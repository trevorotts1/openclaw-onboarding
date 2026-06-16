#!/usr/bin/env python3
"""
sync_check.py — SOP <-> Python LOCKSTEP DETECTOR for the Presentations department.

================================================================================
SOP-LOCKED DEPARTMENT. This is the mechanism that makes the repo *know* — and
FAIL LOUD — when the Python renderer (build_deck.py) and the SOP/role/gate stack
drift apart. A rule not auto-failed at a gate does not exist; lockstep is itself
a gate.
================================================================================

WHAT IT DOES (zero third-party deps — stdlib json / re / ast / pathlib / glob only):
It reconciles FOUR on-disk inputs against the single source of truth
(PIPELINE-MANIFEST.json) in BOTH directions and exits NON-ZERO (4) on any drift:

  1. PIPELINE-MANIFEST.json  — the declared truth (phases / autofails / roles).
  2. build_deck.py           — parsed two ways:
        * AST: the set of `def _chk_*` functions actually defined, and the
          module-level constant names (PROMPT_CHAR_FLOOR, PROMPT_CHAR_CEILING,
          FORBIDDEN_DEMOGRAPHIC_DEFAULTS, ...).
        * regex: every `AF-...` string the source cites (comments + messages).
  3. MASTER-QC-AUTOFAIL-RULESET.md — Section 5 (THE MACHINE-CHECKABLE SUMMARY
        TABLE) parsed row-by-row to the canonical AF-code set.
  4. role-library/presentations/*.md + sops/*.md — the deployed role roster and
        SOP file set.

DRIFT DIRECTIONS (both fail loud with the exact offending item + the fix verb):

  (A) STACK-AHEAD-OF-CODE — a manifest phase / AF code / role / SOP that has no
      matching checker / symbol / registration in build_deck.py (or no Section-5
      row, or no role/SOP file). The stack moved; the code did not.

  (B) CODE-AHEAD-OF-STACK — an orphan `_chk_*` defined in build_deck.py, or an
      orphan `AF-...` string cited in build_deck.py, that the manifest does not
      declare. The code moved; the manifest did not.

EXIT CODES:
    0 — in sync.
    4 — drift (distinct from build_deck's 1/2/3 so a caller can tell lockstep
        drift from a render/config/preflight failure).
    2 — sync_check could not run (an input is missing/unparseable).

USAGE:
    python3 sync_check.py            # human report, exit 0 / 4
    python3 sync_check.py --json     # machine: {"in_sync":bool,"drift":[...]}
    python3 sync_check.py --explain  # also print which EXTENSION-SOP step was skipped

GATES IT RUNS AT (none optional — see SOP-SLIDE-06-EXTENSION-AND-SYNC):
    * QC GATE (Phase 1Q): the QC specialist's mechanical runner executes this
      FIRST; broken lockstep raises AF-SYNC and no deck QC even starts.
    * PRE-COMMIT / CI on openclaw-onboarding: any commit touching a Presentations
      role .md / sops/*.md / the manifest / build_deck.py is blocked on drift.
    * EVERY ONBOARDING UPDATE: the skills-updater runs this as a deploy preflight
      (alongside `openclaw config validate`); a drifted stack is never deployed.
"""

import ast
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Input resolution — everything is found relative to THIS script's location so
# the check runs identically in the repo and on a deployed client box.
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent                       # .../presentations/scripts
PRES_DIR = HERE.parent                                       # .../presentations
SOPS_DIR = PRES_DIR / "sops"
BUILD_DECK = HERE / "build_deck.py"
TEST_PREFLIGHT = HERE / "test_preflight.py"

# The manifest + MASTER ruleset live in the universal-sops/presentation-slide-craft
# cluster in the repo, and are deployed next to the sops dir on a client box. Try
# both so the same script works in either layout.
def _first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return paths[0]  # return the canonical (repo) path for the error message

# repo root = .../openclaw-onboarding (walk up until universal-sops is found)
def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None

_REPO_ROOT = _find_repo_root(HERE)
_CLUSTER_REPO = (_REPO_ROOT / "universal-sops" / "presentation-slide-craft") if _REPO_ROOT else None

MANIFEST = _first_existing([
    *( [_CLUSTER_REPO / "PIPELINE-MANIFEST.json"] if _CLUSTER_REPO else [] ),
    SOPS_DIR / "PIPELINE-MANIFEST.json",
    PRES_DIR / "PIPELINE-MANIFEST.json",
])
MASTER_RULESET = _first_existing([
    *( [_CLUSTER_REPO / "MASTER-QC-AUTOFAIL-RULESET.md"] if _CLUSTER_REPO else [] ),
    SOPS_DIR / "SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md",
    SOPS_DIR / "MASTER-QC-AUTOFAIL-RULESET.md",
    PRES_DIR / "MASTER-QC-AUTOFAIL-RULESET.md",
])

AF_RE = re.compile(r'AF-[A-Z0-9]+(?:-[A-Z0-9]+)*')


# ---------------------------------------------------------------------------
# Fatal-input guard
# ---------------------------------------------------------------------------
def _fatal(msg):
    print(f"FATAL (sync_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# 1. Load the manifest (the declared truth)
# ---------------------------------------------------------------------------
def load_manifest():
    if not MANIFEST.exists():
        _fatal(f"PIPELINE-MANIFEST.json not found (looked at {MANIFEST}).")
    try:
        m = json.loads(MANIFEST.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"PIPELINE-MANIFEST.json is not valid JSON: {exc}")
    for key in ("manifest_version", "phases", "autofails", "roles"):
        if key not in m:
            _fatal(f"PIPELINE-MANIFEST.json missing top-level key {key!r}.")
    if not isinstance(m["manifest_version"], int):
        _fatal("manifest_version must be an integer.")
    return m


# ---------------------------------------------------------------------------
# 2. Parse build_deck.py — AST (defined _chk_*, module constants) + AF strings
# ---------------------------------------------------------------------------
def parse_build_deck():
    if not BUILD_DECK.exists():
        _fatal(f"build_deck.py not found (looked at {BUILD_DECK}).")
    source = BUILD_DECK.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        _fatal(f"build_deck.py does not parse: {exc}")

    chk_funcs = set()
    module_consts = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_chk_"):
            chk_funcs.add(node.name)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    module_consts.add(tgt.id)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                module_consts.add(node.target.id)

    # Every defined name (for py_symbol presence): functions + constants.
    defined_names = set(module_consts)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defined_names.add(node.name)

    af_strings = set(AF_RE.findall(source))

    return {
        "chk_funcs": chk_funcs,
        "module_consts": module_consts,
        "defined_names": defined_names,
        "af_strings": af_strings,
    }


# ---------------------------------------------------------------------------
# 3. Parse the MASTER ruleset Section 5 table -> canonical AF-code set
# ---------------------------------------------------------------------------
def parse_master_ruleset_section5():
    if not MASTER_RULESET.exists():
        _fatal(f"MASTER ruleset not found (looked at {MASTER_RULESET}).")
    text = MASTER_RULESET.read_text()

    # Isolate Section 5 (THE MACHINE-CHECKABLE SUMMARY TABLE). It starts at a
    # heading containing "MACHINE-CHECKABLE SUMMARY TABLE" and runs to EOF (it is
    # the last section) or the next top-level "## " heading.
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "MACHINE-CHECKABLE SUMMARY TABLE" in ln.upper():
            start = i
            break
    if start is None:
        _fatal("MASTER ruleset has no 'MACHINE-CHECKABLE SUMMARY TABLE' section "
               "(Section 5). sync_check parses the AF registry from that table.")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    section = lines[start:end]

    codes = set()
    for ln in section:
        s = ln.strip()
        # table rows look like: | AF-XXX | Stage | Level | Trigger | Detection |
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        # the first cell may carry an alias, e.g. "AF-PLACEHOLDER (AF-AUD-6)".
        for code in AF_RE.findall(first):
            codes.add(code)
    if not codes:
        _fatal("Section 5 table parsed but no AF-* codes were found in column 1. "
               "Has the table shape changed? sync_check expects "
               "'| Code | Stage | Level | Trigger | Detection |' rows.")
    return codes


# ---------------------------------------------------------------------------
# 4. Scan role-library + sops dirs
# ---------------------------------------------------------------------------
def scan_roles_and_sops():
    if not PRES_DIR.is_dir():
        _fatal(f"presentations role-library dir not found: {PRES_DIR}")
    # Role file stems: presentations/*.md, excluding the 00-START-HERE index.
    role_stems = set()
    for p in PRES_DIR.glob("*.md"):
        name = p.stem
        if name.startswith("00-") or name.upper().startswith("00-START"):
            continue
        role_stems.add(name)
    sop_files = set()
    if SOPS_DIR.is_dir():
        for p in SOPS_DIR.glob("*.md"):
            sop_files.add(p.name)
    return role_stems, sop_files


# ---------------------------------------------------------------------------
# THE DRIFT CHECKS
# ---------------------------------------------------------------------------
# AF codes that are render-time constants/comment banners the renderer is ALLOWED
# to cite without being in the SOP Section-5 table or being a phase checker — they
# are classified in the manifest with enforced_by + py_symbol, which is what the
# sync-check validates. (Membership in the manifest is the requirement, not
# membership in the ruleset.)
EXTENSION_STEP = {
    "A1": "step (ii) — add the _chk_ function and register it in build_deck.py",
    "A2": "step (ii) — define the _chk_ function in build_deck.py",
    "A3": "step (ii) — add the constant / _chk_ symbol in build_deck.py",
    "A4": "step (iii) — add the AF code to PIPELINE-MANIFEST.autofails",
    "A5": "step (i) — declare the role in PIPELINE-MANIFEST.roles",
    "A6": "step (i) — point owning_role at a real role-library file",
    "A7": "step (i) — point sop_refs at a real sops/ file",
    "B1": "step (i)+(ii) — declare the phase that uses this checker, or remove the checker",
    "B2": "step (i)+(iii) — register the AF code in PIPELINE-MANIFEST.autofails (and the ruleset)",
}


def run_checks(manifest, bd, ruleset_codes, role_stems, sop_files):
    drift = []  # list of {check, item, detail}

    def add(check, item, detail):
        drift.append({"check": check, "item": item, "detail": detail})

    phases = manifest["phases"]
    autofails = manifest["autofails"]
    roles = manifest["roles"]

    manifest_af_codes = {a["code"] for a in autofails}
    manifest_role_ids = {r["id"] for r in roles}
    chk_funcs = bd["chk_funcs"]
    defined_names = bd["defined_names"]

    # checkers named by manifest phases
    phase_checkers = set()
    for ph in phases:
        pf = ph.get("preflight")
        if pf and pf.get("checker"):
            phase_checkers.add(pf["checker"])
    # _chk_* names referenced by autofail py_symbols (e.g. _chk_coverage via AF-COVERAGE-1)
    autofail_chk_symbols = {a.get("py_symbol") for a in autofails
                            if a.get("py_symbol", "").__class__ is str and a.get("py_symbol", "").startswith("_chk_")}
    referenced_checkers = phase_checkers | autofail_chk_symbols

    # -------- (A) STACK-AHEAD-OF-CODE --------

    # A1 phase -> preflight checker must be a defined _chk_* in build_deck.py
    # A2 manifest checker must be defined (A1/A2 collapse to: the named checker exists)
    for ph in phases:
        pf = ph.get("preflight")
        if not pf or not pf.get("required"):
            continue
        checker = pf.get("checker")
        if not checker:
            add("A1", ph["id"],
                f"phase {ph['id']} has preflight.required:true but names no checker. "
                f"{EXTENSION_STEP['A1']}.")
            continue
        if checker not in chk_funcs:
            add("A2", checker,
                f"manifest phase {ph['id']} names checker {checker!r}, which is not "
                f"defined as a `def {checker}` in build_deck.py. {EXTENSION_STEP['A2']}.")

    # A3 AF row enforced_by build_deck -> py_symbol must exist in build_deck.py
    for a in autofails:
        if a.get("enforced_by") == "build_deck":
            sym = a.get("py_symbol")
            if not sym:
                add("A3", a["code"],
                    f"AF {a['code']} is declared enforced_by:build_deck but has no "
                    f"py_symbol. {EXTENSION_STEP['A3']}.")
            elif sym not in defined_names:
                add("A3", a["code"],
                    f"AF {a['code']} is declared build_deck-enforced via {sym!r}, which "
                    f"does not exist in build_deck.py (not a defined _chk_/function/constant). "
                    f"{EXTENSION_STEP['A3']}.")

    # A4 every Section-5 ruleset code must be present in manifest.autofails
    for code in sorted(ruleset_codes):
        if code not in manifest_af_codes:
            add("A4", code,
                f"AF {code} is in the MASTER ruleset Section 5 but absent from "
                f"PIPELINE-MANIFEST.autofails. {EXTENSION_STEP['A4']} "
                f"(classify enforced_by + py_symbol).")

    # A5 every shipped role file stem must be declared in manifest.roles
    for stem in sorted(role_stems):
        if stem not in manifest_role_ids:
            add("A5", stem,
                f"role {stem} ships in the role library but is not in "
                f"PIPELINE-MANIFEST.roles. {EXTENSION_STEP['A5']} "
                f"(declare its owns_phase, or null).")

    # A6 every phase owning_role must be a real role file stem
    for ph in phases:
        owner = ph.get("owning_role")
        if owner and owner not in role_stems:
            add("A6", ph["id"],
                f"phase {ph['id']} owning_role {owner!r} has no role-library file "
                f"(presentations/{owner}.md). {EXTENSION_STEP['A6']}.")

    # A7 every phase sop_refs file (pre-'#') must exist in the sops dir
    for ph in phases:
        for ref in ph.get("sop_refs", []):
            fname = str(ref).split("#", 1)[0].strip()
            if not fname:
                continue
            if fname not in sop_files:
                add("A7", f"{ph['id']}:{fname}",
                    f"phase {ph['id']} references SOP {fname!r}, which is not present "
                    f"in the sops dir ({SOPS_DIR}). {EXTENSION_STEP['A7']}.")

    # -------- (B) CODE-AHEAD-OF-STACK --------

    # B1 orphan _chk_* defined in build_deck.py but referenced by no manifest
    #    phase checker AND no autofail py_symbol.
    for fn in sorted(chk_funcs):
        if fn not in referenced_checkers:
            add("B1", fn,
                f"build_deck.py defines {fn} but no manifest phase preflight.checker "
                f"and no autofails[].py_symbol references it. {EXTENSION_STEP['B1']}.")

    # B2 orphan AF-* string cited in build_deck.py but absent from manifest.autofails
    for code in sorted(bd["af_strings"]):
        if code not in manifest_af_codes:
            add("B2", code,
                f"build_deck.py cites {code} but it is absent from "
                f"PIPELINE-MANIFEST.autofails. A renderer must not cite an unregistered "
                f"AF code. {EXTENSION_STEP['B2']}.")

    return drift


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def report_human(drift, manifest, explain):
    if not drift:
        print("=== sync_check: PRESENTATIONS SOP <-> build_deck.py LOCKSTEP ===")
        print(f"manifest_version: {manifest['manifest_version']}")
        print(f"phases: {len(manifest['phases'])}  autofails: {len(manifest['autofails'])}  "
              f"roles: {len(manifest['roles'])}")
        print("IN SYNC — the Python renderer, the MASTER ruleset Section-5 table, the "
              "role roster, and the SOP set all match PIPELINE-MANIFEST.json.")
        return
    a = [d for d in drift if d["check"].startswith("A")]
    b = [d for d in drift if d["check"].startswith("B")]
    print("=== sync_check: DRIFT DETECTED — LOCKSTEP BROKEN (AF-SYNC) ===", file=sys.stderr)
    if a:
        print("\n(A) STACK-AHEAD-OF-CODE — the SOP/role/gate stack moved; build_deck.py "
              "(or the manifest) did not:", file=sys.stderr)
        for d in a:
            print(f"  DRIFT {d['check']}: [{d['item']}] {d['detail']}", file=sys.stderr)
    if b:
        print("\n(B) CODE-AHEAD-OF-STACK — build_deck.py moved; the manifest/ruleset "
              "did not:", file=sys.stderr)
        for d in b:
            print(f"  DRIFT {d['check']}: [{d['item']}] {d['detail']}", file=sys.stderr)
    print(f"\n{len(drift)} drift item(s). See SOP-SLIDE-06-EXTENSION-AND-SYNC: any "
          "change to a Presentations SOP/role/gate MUST update PIPELINE-MANIFEST.json "
          "(+ bump manifest_version), build_deck.py, the MASTER ruleset, and a test.",
          file=sys.stderr)


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    explain = "--explain" in argv

    manifest = load_manifest()
    bd = parse_build_deck()
    ruleset_codes = parse_master_ruleset_section5()
    role_stems, sop_files = scan_roles_and_sops()

    drift = run_checks(manifest, bd, ruleset_codes, role_stems, sop_files)

    if as_json:
        print(json.dumps({
            "in_sync": not drift,
            "manifest_version": manifest["manifest_version"],
            "counts": {"phases": len(manifest["phases"]),
                       "autofails": len(manifest["autofails"]),
                       "roles": len(manifest["roles"])},
            "drift": drift,
        }, indent=2))
    else:
        report_human(drift, manifest, explain)

    sys.exit(4 if drift else 0)


if __name__ == "__main__":
    main()
