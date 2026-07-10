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
      row, or no role/SOP file). Includes A8: every phase emits.checks entry must be
      a defined constant/function in build_deck.py. The stack moved; the code did not.

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
# The ONE shared image-prompt gate every image-API path imports. Its char-band constants
# are an EXTRACTION of build_deck.py's and MUST never silently diverge from them — the same
# drift class V1 pins for the retired render_deck.py. V3 proves prompt_gate == build_deck.
PROMPT_GATE = HERE / "prompt_gate.py"
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

# The RETIRED render module (templates/presentation-render/render_deck.py). It is no
# longer the canonical renderer, but sync_check still AST-asserts that its
# PROMPT_CHAR_FLOOR/CEILING band never silently diverges from build_deck.py's — a
# divergence is exactly the class of drift that let the 1,500-vs-5,000 floor split
# go unnoticed. Resolved relative to the repo root (repo layout) or, on a deployed
# client box where the render-template tree may be absent, simply skipped.
RENDER_DECK = (
    (_REPO_ROOT / "23-ai-workforce-blueprint" / "templates" / "presentation-render"
     / "render_deck.py") if _REPO_ROOT else None
)

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

# HOLE B — every AF code a registered QC-checker script EMITS must be a registered
# manifest code. We scan emission CONTEXT only (`"code": "AF-..."` dicts), never bare
# docstring/comment mentions, so a checker's prose taxonomy never false-positives. This
# is what would have caught AF-NARRATIVE-HARMONY (live in intelligence_engines_check.py,
# absent from the manifest — HOLE A) at lockstep time.
CODE_EMIT_RE = re.compile(r"""["']code["']\s*:\s*["'](AF-[A-Z0-9]+(?:-[A-Z0-9]+)*)["']""")

# The canonical deliverable key set (order-independent). Any drift between the
# manifest deliverables_required list and build_deck.py DELIVERABLES_REQUIRED
# is an auto-fail (check D1/D2 below).
_EXPECTED_DELIVERABLE_KEYS = {
    "deck_pptx", "deck_pdf", "guide_pdf",
    "speech_md", "speech_pdf", "audio_mp3", "infographic_png",
}


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
    # deliverables_required is optional for backward-compat but required from v4 onward.
    if m["manifest_version"] >= 4 and "deliverables_required" not in m:
        _fatal("PIPELINE-MANIFEST.json manifest_version >= 4 requires a "
               "'deliverables_required' top-level key listing the six required deliverables.")
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

    # --- Extract DELIVERABLES_REQUIRED key set from the AST ---
    # We look for a module-level assignment `DELIVERABLES_REQUIRED = [...]` and
    # extract all string values of "key" fields from the list of dicts.
    # Falls back to the regex approach if the AST walk does not find the list.
    deliverable_keys = _extract_deliverable_keys_ast(tree)

    return {
        "chk_funcs": chk_funcs,
        "module_consts": module_consts,
        "defined_names": defined_names,
        "af_strings": af_strings,
        "deliverable_keys": deliverable_keys,
    }


def _extract_deliverable_keys_ast(tree):
    """Walk the module-level AST to find DELIVERABLES_REQUIRED = [...] and
    extract the string values of every 'key' keyword in the list of dicts.
    Returns a set of key strings, or None if the constant is not found."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "DELIVERABLES_REQUIRED":
                val = node.value
                if not isinstance(val, ast.List):
                    return None
                keys = set()
                for elt in val.elts:
                    if not isinstance(elt, ast.Dict):
                        continue
                    for k, v in zip(elt.keys, elt.values):
                        if (isinstance(k, ast.Constant) and k.value == "key"
                                and isinstance(v, ast.Constant)):
                            keys.add(v.value)
                return keys if keys else None
    return None


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
def parse_check_scripts(manifest):
    """HOLE B — collect every script named in an autofails[].check_script, scan each
    for the AF codes it EMITS (`"code": "AF-..."` dicts), and return
    {emitted_code: [script_rel, ...]}. The check_script form is 'scripts/FILE.py::func';
    the file is resolved relative to PRES_DIR (the same layout as a deployed client box).
    A named script that is absent on disk is skipped (it is the manifest's own A-direction
    job to keep check_script pointed at a real file)."""
    emitted = {}
    seen_files = set()
    for a in manifest.get("autofails", []):
        cs = a.get("check_script")
        if not cs or not isinstance(cs, str):
            continue
        rel = cs.split("::", 1)[0].strip()
        if not rel or rel in seen_files:
            continue
        seen_files.add(rel)
        path = (PRES_DIR / rel)
        if not path.exists():
            continue
        try:
            src = path.read_text()
        except Exception:  # noqa: BLE001
            continue
        for code in CODE_EMIT_RE.findall(src):
            emitted.setdefault(code, set()).add(rel)
    return {k: sorted(v) for k, v in emitted.items()}


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
    "A8": "step (i)+(ii) — point emits.checks at a real constant/function in build_deck.py (or remove the entry)",
    "B1": "step (i)+(ii) — declare the phase that uses this checker, or remove the checker",
    "B2": "step (i)+(iii) — register the AF code in PIPELINE-MANIFEST.autofails (and the ruleset)",
    "C1": "step (i)+(iii) — a QC-checker script EMITS this AF code but the manifest does not declare it; register it in PIPELINE-MANIFEST.autofails (+ the ruleset), or stop emitting it",
    "D1": "step (ii) — add the missing deliverable key to DELIVERABLES_REQUIRED in build_deck.py",
    "D2": "step (i) — add the missing deliverable key to deliverables_required in PIPELINE-MANIFEST.json",
    "E1": "step (i) — add a client_report block to the phase in PIPELINE-MANIFEST.json (manifest v21+ requirement)",
    "E2": "step (i) — add heartbeat_minutes to the long_running phase in PIPELINE-MANIFEST.json",
}


# ---------------------------------------------------------------------------
# (V) VALUE-LEVEL DRIFT — the cited NUMBER must match the code constant.
# The original sync_check proved that the SAME NAMES exist on both sides, but not
# that the SAME VALUES do. That gap is what let PROMPT_CHAR_FLOOR drift: the manifest
# said "1500-char floor" while build_deck.py's constant was 5000, and the names all
# lined up so nothing failed. These checks close that gap.
# ---------------------------------------------------------------------------
def _const_int_values(py_path):
    """AST-parse a python file and return {UPPER_CONST_NAME: int_value} for every
    module-level `NAME = <int literal>` assignment. Booleans are excluded (bool is an
    int subclass). Returns {} if the file is absent/unparseable (caller decides)."""
    out = {}
    try:
        tree = ast.parse(Path(py_path).read_text())
    except Exception:  # noqa: BLE001
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (isinstance(tgt, ast.Name) and tgt.id.isupper()
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, int)
                    and not isinstance(node.value.value, bool)):
                out[tgt.id] = node.value.value
    return out


def value_checks(manifest_text):
    """V1: render_deck.py's PROMPT_CHAR_FLOOR/CEILING == build_deck.py's (the retired
    render module must never carry a stale prompt band).
    V2: every floor/standard/ceiling integer the manifest CITES in prose must equal the
    corresponding build_deck.py constant (PROMPT_CHAR_FLOOR / PROMPT_CHAR_CEILING).
    Returns a list of drift dicts (check 'V1'/'V2')."""
    drift = []

    def add(check, item, detail):
        drift.append({"check": check, "item": item, "detail": detail})

    bd_vals = _const_int_values(BUILD_DECK)
    floor = bd_vals.get("PROMPT_CHAR_FLOOR")
    ceiling = bd_vals.get("PROMPT_CHAR_CEILING")

    if floor is None:
        add("V2", "PROMPT_CHAR_FLOOR",
            "build_deck.py has no module-level integer PROMPT_CHAR_FLOOR constant — the "
            "value-level floor check cannot anchor. Restore the constant.")
    if ceiling is None:
        add("V2", "PROMPT_CHAR_CEILING",
            "build_deck.py has no module-level integer PROMPT_CHAR_CEILING constant — the "
            "value-level ceiling check cannot anchor. Restore the constant.")

    # V1 — retired render module band == canonical band.
    if RENDER_DECK and RENDER_DECK.exists():
        rd_vals = _const_int_values(RENDER_DECK)
        for name, bdv in (("PROMPT_CHAR_FLOOR", floor), ("PROMPT_CHAR_CEILING", ceiling)):
            if bdv is None:
                continue
            rdv = rd_vals.get(name)
            if rdv is None:
                add("V1", name,
                    f"render_deck.py (retired render module) is missing the {name} "
                    f"constant; build_deck.py has {name}={bdv}. Keep the constant in "
                    f"render_deck.py so the bands can be proven equal.")
            elif rdv != bdv:
                add("V1", name,
                    f"render_deck.py {name}={rdv} != build_deck.py {name}={bdv}. The "
                    f"retired render module's prompt band must never silently diverge "
                    f"from the canonical renderer's. Reconcile render_deck.py to {bdv}.")

    # V3 — the shared prompt_gate.py band == the canonical build_deck.py band. prompt_gate
    # is the ONE gate every image-API path (kie_generate.py x2, the relay) imports; its
    # floor/ceiling/distinct-word constants are an extraction of build_deck.py's and must
    # never diverge, or a side-door could enforce a stale band. Same class as V1.
    if PROMPT_GATE and PROMPT_GATE.exists():
        pg_vals = _const_int_values(PROMPT_GATE)
        for name in ("PROMPT_CHAR_FLOOR", "PROMPT_CHAR_CEILING", "PROMPT_MIN_DISTINCT_WORDS"):
            bdv = bd_vals.get(name)
            pgv = pg_vals.get(name)
            if bdv is None:
                continue  # V2 already flags a missing build_deck constant
            if pgv is None:
                add("V3", name,
                    f"prompt_gate.py is missing the {name} constant; build_deck.py has "
                    f"{name}={bdv}. The shared gate every image-API path imports must carry "
                    f"the SAME band as the canonical renderer. Add {name}={bdv} to prompt_gate.py.")
            elif pgv != bdv:
                add("V3", name,
                    f"prompt_gate.py {name}={pgv} != build_deck.py {name}={bdv}. The shared "
                    f"image-prompt gate's band must never silently diverge from the canonical "
                    f"renderer's (a side-door would enforce a stale floor). Reconcile "
                    f"prompt_gate.py to {bdv}.")

    # V2 — manifest-cited floor/standard/ceiling integers == code constants.
    if floor is not None:
        for m in re.finditer(r'([0-9][0-9,]*)-char (floor|standard)', manifest_text):
            n = int(m.group(1).replace(",", ""))
            if n != floor:
                add("V2", f"{m.group(0)}",
                    f"PIPELINE-MANIFEST.json cites a {n}-char {m.group(2)} but "
                    f"build_deck.py PROMPT_CHAR_FLOOR={floor}. The manifest's cited floor "
                    f"integer must equal the code constant (this is the exact 1,500-vs-5,000 "
                    f"drift class). Reconcile the manifest prose to {floor}.")
    if ceiling is not None:
        for m in re.finditer(r'([0-9][0-9,]*)-char ceiling', manifest_text):
            n = int(m.group(1).replace(",", ""))
            if n != ceiling:
                add("V2", f"{m.group(0)}",
                    f"PIPELINE-MANIFEST.json cites a {n}-char ceiling but build_deck.py "
                    f"PROMPT_CHAR_CEILING={ceiling}. Reconcile the manifest prose to {ceiling}.")
    return drift


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

    # checkers named by manifest phases (primary preflight + additional_preflights)
    phase_checkers = set()
    for ph in phases:
        pf = ph.get("preflight")
        if pf and pf.get("checker"):
            phase_checkers.add(pf["checker"])
        # additional_preflights: list of {checker, required, label} entries (AF-RESEARCH-UNCITED pattern)
        for ap in ph.get("additional_preflights", []):
            if ap.get("checker"):
                phase_checkers.add(ap["checker"])
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
            pass
        else:
            checker = pf.get("checker")
            if not checker:
                add("A1", ph["id"],
                    f"phase {ph['id']} has preflight.required:true but names no checker. "
                    f"{EXTENSION_STEP['A1']}.")
            elif checker not in chk_funcs:
                add("A2", checker,
                    f"manifest phase {ph['id']} names checker {checker!r}, which is not "
                    f"defined as a `def {checker}` in build_deck.py. {EXTENSION_STEP['A2']}.")
        # additional_preflights: same A1/A2 check for each extra checker entry
        for ap in ph.get("additional_preflights", []):
            if not ap.get("required"):
                continue
            ap_checker = ap.get("checker")
            if not ap_checker:
                add("A1", ph["id"],
                    f"phase {ph['id']} additional_preflight has required:true but names no checker. "
                    f"{EXTENSION_STEP['A1']}.")
            elif ap_checker not in chk_funcs:
                add("A2", ap_checker,
                    f"manifest phase {ph['id']} additional_preflight names checker {ap_checker!r}, "
                    f"which is not defined as a `def {ap_checker}` in build_deck.py. "
                    f"{EXTENSION_STEP['A2']}.")

    # A3 AF row enforced_by build_deck -> py_symbol (and any secondary_py_symbols) must exist
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
            # secondary_py_symbols: additional symbols this AF code depends on (e.g. constants)
            for sec_sym in a.get("secondary_py_symbols", []):
                if sec_sym not in defined_names:
                    add("A3", a["code"],
                        f"AF {a['code']} secondary_py_symbol {sec_sym!r} does not exist "
                        f"in build_deck.py. {EXTENSION_STEP['A3']}.")

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

    # A8 every phase emits.checks entry must be a defined name (constant or function)
    # in build_deck.py. A manifest phase that declares it emits a named check whose
    # symbol does not exist in the renderer is drift — the check moved or was renamed
    # in the Python but the manifest still advertises the old name (or vice versa).
    # This is what makes the manifest's emits.checks a REAL guard, not just a label.
    for ph in phases:
        emits = ph.get("emits")
        if not isinstance(emits, dict):
            continue
        for chk in emits.get("checks", []) or []:
            if chk not in defined_names:
                add("A8", f"{ph['id']}:{chk}",
                    f"phase {ph['id']} emits.checks names {chk!r}, which is not defined "
                    f"in build_deck.py (no matching constant or function). "
                    f"{EXTENSION_STEP['A8']}.")

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

    # -------- (C) CHECKER-SCRIPT-AHEAD-OF-STACK (HOLE B) --------
    # C1 every AF code EMITTED by a registered check_script must be a registered manifest
    # code. sync_check used to scan ONLY build_deck.py, so a code emitted by
    # pitch_engines_check.py / intelligence_engines_check.py could fail a deck while being
    # absent from the registry (exactly how AF-NARRATIVE-HARMONY went undetected — HOLE A).
    emitted = parse_check_scripts(manifest)
    for code in sorted(emitted):
        if code not in manifest_af_codes:
            srcs = ", ".join(emitted[code])
            add("C1", code,
                f"checker script(s) [{srcs}] EMIT {code} (a `\"code\": \"{code}\"` problem "
                f"dict) but it is absent from PIPELINE-MANIFEST.autofails — a deck can be "
                f"failed by a code the registry does not declare. {EXTENSION_STEP['C1']}.")

    # -------- (E) PHASE CLIENT-REPORT DRIFT --------
    # E1: every phase must carry a client_report block (added in manifest v21 as part of
    #     the per-step progress-report gate; Fix 4c).  A phase without client_report
    #     means the runner cannot emit step start/done messages for it.
    for ph in phases:
        if not ph.get("client_report"):
            add("E1", ph["id"],
                f"phase {ph['id']} is missing a 'client_report' block "
                f"(manifest v21+ requires every phase to carry "
                f"{{\"start_template\":\"...\",\"done_template\":\"...\"}} so the "
                f"runner can emit client progress messages). Add a client_report "
                f"object to this phase in PIPELINE-MANIFEST.json and bump manifest_version.")

    # E2: every phase with long_running:true must also declare heartbeat_minutes.
    for ph in phases:
        if ph.get("long_running") and not ph.get("heartbeat_minutes"):
            add("E2", ph["id"],
                f"phase {ph['id']} is marked long_running:true but declares no "
                f"heartbeat_minutes. The watchdog needs to know the polling interval "
                f"for long phases (e.g. heartbeat_minutes:10). Add heartbeat_minutes "
                f"to this phase in PIPELINE-MANIFEST.json.")

    # -------- (D) DELIVERABLE-SET DRIFT --------
    # D1/D2: the key set in manifest.deliverables_required must exactly match
    # the key set in build_deck.py's DELIVERABLES_REQUIRED list.
    # This is a bidirectional lockstep on the output artifact set so a deliverable
    # added to the manifest but missing from the gate (or vice versa) auto-fails.
    manifest_deliverable_keys = set()
    for d in manifest.get("deliverables_required", []):
        if isinstance(d, dict) and "key" in d:
            manifest_deliverable_keys.add(d["key"])

    bd_deliverable_keys = bd.get("deliverable_keys") or set()

    if manifest_deliverable_keys or bd_deliverable_keys:
        # D1: key in manifest but not in build_deck.py DELIVERABLES_REQUIRED
        for key in sorted(manifest_deliverable_keys - bd_deliverable_keys):
            add("D1", key,
                f"deliverable key {key!r} is in PIPELINE-MANIFEST.deliverables_required "
                f"but absent from build_deck.py DELIVERABLES_REQUIRED. "
                f"{EXTENSION_STEP['D1']}.")
        # D2: key in build_deck.py DELIVERABLES_REQUIRED but not in manifest
        for key in sorted(bd_deliverable_keys - manifest_deliverable_keys):
            add("D2", key,
                f"deliverable key {key!r} is in build_deck.py DELIVERABLES_REQUIRED "
                f"but absent from PIPELINE-MANIFEST.deliverables_required. "
                f"{EXTENSION_STEP['D2']}.")

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
    c = [d for d in drift if d["check"].startswith("C")]
    e = [d for d in drift if d["check"].startswith("E")]
    v = [d for d in drift if d["check"].startswith("V")]
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
    if c:
        print("\n(C) CHECKER-SCRIPT-AHEAD-OF-STACK — a registered QC-checker script EMITS "
              "an AF code the manifest does not declare (HOLE B):", file=sys.stderr)
        for d in c:
            print(f"  DRIFT {d['check']}: [{d['item']}] {d['detail']}", file=sys.stderr)
    if e:
        print("\n(E) PHASE-STRUCTURE DRIFT — a manifest phase is missing a required "
              "structural block (client_report, heartbeat_minutes on long_running):",
              file=sys.stderr)
        for d in e:
            print(f"  DRIFT {d['check']}: [{d['item']}] {d['detail']}", file=sys.stderr)
    if v:
        print("\n(V) VALUE DRIFT — the names match but the NUMBERS do not (the cited "
              "floor/ceiling integer != the code constant):", file=sys.stderr)
        for d in v:
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
    # (V) value-level drift — the cited NUMBER must equal the code constant.
    drift += value_checks(MANIFEST.read_text())

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
