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

DRIFT CLASS (FIX-23(a)) — every drift item in the `--json` output carries a `class`
  field so the canonical door (presentation-canonical-entry.sh GATE 3) can tell
  SOP-LIBRARY maintenance debt from RENDER-PATH drift:
    "A5/A6"       — library-only. Undeclared roles / owning_role -> missing .md.
                    Does NOT change render correctness. GATE 3 PROCEEDS (evented),
                    so library maintenance debt can never brick the sanctioned door.
    "render_path" — every other class (A1-A4/A7/A8, B*, C*, D*, E*, V*). The actual
                    renderer has drifted from the manifest/ruleset. GATE 3 FAILS
                    CLOSED (AF-CANONICAL-RENDER-BYPASS / exit 7), exactly as before.

EXIT CODES:
    0 — in sync.
    4 — drift (distinct from build_deck's 1/2/3 so a caller can tell lockstep
        drift from a render/config/preflight failure).
    2 — sync_check could not run (an input is missing/unparseable).
       Warn-mode (W*) findings never change the exit code; see --json "warn_count".

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
sys.path.insert(0, str(HERE))
from manifest_source import resolve_manifest, resolve_ruleset, refuse, find_repo_root
PRES_DIR = HERE.parent                                       # .../presentations
SOPS_DIR = PRES_DIR / "sops"
BUILD_DECK = HERE / "build_deck.py"
# The ONE shared image-prompt gate every image-API path imports. Its char-band constants
# are an EXTRACTION of build_deck.py's and MUST never silently diverge from them — the same
# drift class V1 pins for the retired render_deck.py. V3 proves prompt_gate == build_deck.
PROMPT_GATE = HERE / "prompt_gate.py"
TEST_PREFLIGHT = HERE / "test_preflight.py"

_REPO_ROOT = find_repo_root(HERE)
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

MANIFEST, MANIFEST_PROVENANCE = resolve_manifest(HERE)
MASTER_RULESET, RULESET_PROVENANCE = resolve_ruleset(HERE)

# Measured 2026-07-25 via parse_master_ruleset_section5() against the cluster
# registry at universal-sops/presentation-slide-craft/MASTER-QC-AUTOFAIL-RULESET.md.
# The cluster registry is a growing file (134 codes against 153 manifest autofails
# at time of measurement), so this is a FLOOR, not an equality — a future increase
# is expected and must not refuse.
RULESET_MIN_SECTION5_CODES = 134

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

    Mirrors the manifest-side D1/D2 filter: a deliverable dict carrying
    `produced_later: True` (Feature L2-G — e.g. webinar_mp4 at P9.6-WEBINAR-VIDEO,
    order 8.92) is produced AFTER build_deck's P8 assembly postflight gate and is
    skipped by that gate, so it is intentionally NOT part of the D1/D2 lockstep set
    on EITHER side. build_deck.py still declares it in DELIVERABLES_REQUIRED (with
    produced_later: True) so the postflight skips it explicitly rather than treating
    it as missing; sync_check therefore excludes it from the cross-checked key set
    exactly as the manifest-side code does, so the two sides cannot drift.

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
                    # Collect the key/value pairs once, then decide membership:
                    # a produced_later:True entry is excluded from the lockstep set.
                    kv = {}
                    for k, v in zip(elt.keys, elt.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            kv[k.value] = v.value
                    key = kv.get("key")
                    if key and not kv.get("produced_later"):
                        keys.add(key)
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


# Directories under the department root that are infrastructure, never roles. Each
# ships its own how-to.md, so without this set the directory rule below would register
# them as roles — the identical false-positive class the rule exists to remove.
# Measured 2026-07-25 on the deployed department: 60 dirs contain how-to.md; 3 of them
# (memory, scripts, sops) are infra; 57 are roles; 35 unique after de-numbering.
_INFRA_DIRS = {"scripts", "sops", "memory", "working", ".openclaw"}

# Flat *.md files at the department root that are agent scaffolding, not roles. They
# are declared in PIPELINE-MANIFEST.roles today; U009 removes them from the manifest in
# THIS SAME COMMIT, and without this set that removal creates five new A5 items.
_NON_ROLE_DOCS = {"BUILDER-PROMPT", "IDENTITY", "SOUL", "TOOLS",
                  "how-to-use-this-department",
                  # Fleet-scaffolding docs that the fleet sync copies into every
                  # department dir (NOT department roles). They must not count as
                  # un-declared roles (A5) on a DEPLOYED layout — FIX-23c repaired
                  # the repo (which has no such files) but the deployed dept dirs
                  # carry them, so excluding here closes the 27-drift debt for the
                  # fleet-deployed layouts too.
                  "AGENTS", "DREAMS", "HEARTBEAT", "MEMORY", "USER",
                  # Fleet-deployed scaffolding seen on client boxes (verified during
                  # the Loop-2 fleet roll): a fleet-generated ROSTER.md and a
                  # governing-personas.md ship into deployed department dirs but are
                  # not department roles. Exclude them so A5 does not false-DRIFT a
                  # box that is fully on the current manifest (FIX-23c + roll fix).
                  "ROSTER", "GOVERNING-PERSONAS"}


def scan_roles_and_sops():
    if not PRES_DIR.is_dir():
        _fatal(f"presentations role-library dir not found: {PRES_DIR}")
    # Role file stems, layout-agnostic. The repo library ships each role as a flat
    # <slug>.md; the deployed department ships each role as <NN->?<slug>/how-to.md.
    # Both are accepted so the same checker is honest in both layouts.
    role_stems = set()
    for p in PRES_DIR.glob("*.md"):
        name = p.stem
        if name.startswith("00-") or name.upper().startswith("00-START"):
            continue
        if name in _NON_ROLE_DOCS:
            continue
        role_stems.add(name)
    for d in PRES_DIR.iterdir():
        if not d.is_dir() or d.name in _INFRA_DIRS:
            continue
        if (d / "how-to.md").exists():
            role_stems.add(re.sub(r"^\d\d-", "", d.name))
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
    "E3": "step (i) — add a sane positive heartbeat_minutes value to this phase in PIPELINE-MANIFEST.json (every phase requires one, not only long_running:true phases)",
}

# WARN-MODE classes. These are ADVISORY: they are collected in a SEPARATE list from
# `drift`, they never contribute to the exit code, and they never flip --json's
# "in_sync". Letter W is chosen because A/B/C/D/E/V are all in use as drift classes
# (A1-A8, B1-B2, C1, D1-D2, E1-E3 in EXTENSION_STEP, plus V1/V2/V3 emitted by
# value_checks()). Reusing A7 — as an earlier draft proposed — would have attached
# an exit-0 meaning to the live sop_refs integrity class at :587-596.
WARN_STEP = {
    "W1": "step (i) — declare executor and verifier on the phase in PIPELINE-MANIFEST.json "
          "(the step contract). ADVISORY until every phase carries both; then this class "
          "is promoted to fail-closed in a separate unit.",
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
        # FIX-23(a) — V-class is render-path (the cited NUMBER must equal the code
        # constant); fail closed. Same `class` contract as run_checks().
        drift.append({"check": check, "item": item, "detail": detail, "class": "render_path"})

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


def warn_checks(manifest):
    """W1 — the STEP CONTRACT, in warn-mode (Rule 3.5 stage 1).

    Every phase should declare BOTH `executor` (who runs the step) and `verifier` (what
    proves it ran). Measured 2026-07-25: zero of 20 phases in the installed v18 manifest
    and zero of 26 in the canonical v25 manifest declare `executor`, and `verifier` is
    not a field in either. A fail-closed version of this check would therefore fail every
    phase on day one, so it reports and returns; the count IS the work list.

    Returns a list of {check, item, detail} dicts for the SEPARATE warnings list. It must
    never be added to `drift`: main() exits 4 on any drift entry, and two callers treat
    non-zero as a hard stop (the CI lockstep job, and presentation-canonical-entry.sh's
    GATE 3, which maps it to AF-CANONICAL-RENDER-BYPASS / exit 7)."""
    warns = []
    for ph in manifest["phases"]:
        missing = [k for k in ("executor", "verifier") if not ph.get(k)]
        if missing:
            warns.append({
                "check": "W1",
                "item": ph["id"],
                "detail": (f"phase {ph['id']} declares no {' and no '.join(missing)}. "
                           f"{WARN_STEP['W1']}"),
            })
    return warns


def run_checks(manifest, bd, ruleset_codes, role_stems, sop_files):
    drift = []  # list of {check, item, detail, class}

    def add(check, item, detail):
        # FIX-23(a) — every drift item carries a `class` so the canonical door
        # (GATE 3) can tell SOP-LIBRARY maintenance debt from RENDER-PATH drift.
        # A5 (undeclared roles) and A6 (owning_role -> missing .md) are library-only:
        # they do not change render correctness and MUST NOT brick the render path.
        # Every other class (A1-A4/A7/A8, B*, C*, D*, E*, V*) is render-path: the
        # actual renderer has drifted from the manifest/ruleset and must fail closed.
        if check in ("A5", "A6"):
            cls = "A5/A6"  # library-only
        else:
            cls = "render_path"
        drift.append({"check": check, "item": item, "detail": detail, "class": cls})

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

    # E3: EVERY phase — not just long_running ones — must carry a heartbeat_minutes
    # value, and it must be a sane positive integer. WI-10 (CHANGELOG v22.0.5)
    # deliberately put heartbeat_minutes on all 36 phases, not only the 3 marked
    # long_running:true; E2 alone only re-derives that 3-phase subset and is
    # presence-only for it, so stripping the field from the other 33 phases (a full
    # revert of WI-10 everywhere except the long_running phases) produced ZERO drift
    # items and sync_check kept exiting 0 — the anti-silence watchdog protection can
    # evaporate from 33 of 36 phases with no alarm. E3 closes that hole: it is a
    # structural assertion on every phase, independent of long_running, and it names
    # every offending phase rather than passing on a single instance.
    for ph in phases:
        hb = ph.get("heartbeat_minutes")
        if hb is None:
            add("E3", ph["id"],
                f"phase {ph['id']} declares no heartbeat_minutes. Manifest v45+ "
                f"(WI-10) requires EVERY phase — not only long_running:true ones — "
                f"to carry a heartbeat_minutes value so the watchdog always knows "
                f"the client-report polling interval. Add heartbeat_minutes to this "
                f"phase in PIPELINE-MANIFEST.json.")
        elif not isinstance(hb, int) or isinstance(hb, bool) or hb <= 0:
            add("E3", ph["id"],
                f"phase {ph['id']} declares heartbeat_minutes={hb!r}, which is not a "
                f"sane positive integer. heartbeat_minutes must be a whole number of "
                f"minutes > 0 (the manifest's existing values run 15-120). Fix the "
                f"value for this phase in PIPELINE-MANIFEST.json.")

    # -------- (D) DELIVERABLE-SET DRIFT --------
    # D1/D2: the key set in manifest.deliverables_required must exactly match
    # the key set in build_deck.py's DELIVERABLES_REQUIRED list.
    # This is a bidirectional lockstep on the output artifact set so a deliverable
    # added to the manifest but missing from the gate (or vice versa) auto-fails.
    # EXCEPTION (Feature L2-G): a deliverable marked `produced_later: true` is produced
    # by a phase that runs AFTER build_deck's P8 assembly postflight (e.g. webinar_mp4
    # at P9.6-WEBINAR-VIDEO, order 8.92). build_deck's postflight gate MUST NOT require
    # it (that gate runs at assembly, before the later phase), so it is intentionally
    # absent from build_deck.DELIVERABLES_REQUIRED and is NOT subject to D1. It is still
    # wired into build_bundle_files / client_package_files and gated by
    # fix_bundle_complete.py + delivery_gate.py, which run at closeout.
    manifest_deliverable_keys = set()
    for d in manifest.get("deliverables_required", []):
        if isinstance(d, dict) and "key" in d and not d.get("produced_later"):
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
def _print_warnings(warnings, manifest):
    if warnings:
        print(f"\n(W) STEP-CONTRACT WARNINGS — ADVISORY, exit code unaffected "
              f"({len(warnings)} of {len(manifest['phases'])} phases):", file=sys.stderr)
        for w in warnings:
            print(f"  WARN {w['check']}: [{w['item']}] {w['detail']}", file=sys.stderr)
        print(f"\n{len(warnings)} warning(s). These do NOT fail the check. Drive the count "
              f"to zero, then promote W1 to fail-closed in a separate change.", file=sys.stderr)


def report_human(drift, warnings, manifest, explain):
    if not drift:
        print("=== sync_check: PRESENTATIONS SOP <-> build_deck.py LOCKSTEP ===")
        print(f"manifest_version: {manifest['manifest_version']}")
        print(f"phases: {len(manifest['phases'])}  autofails: {len(manifest['autofails'])}  "
              f"roles: {len(manifest['roles'])}")
        print("IN SYNC — the Python renderer, the MASTER ruleset Section-5 table, the "
              "role roster, and the SOP set all match PIPELINE-MANIFEST.json.")
        _print_warnings(warnings, manifest)
        return
    a = [d for d in drift if d["check"].startswith("A")]
    b = [d for d in drift if d["check"].startswith("B")]
    c = [d for d in drift if d["check"].startswith("C")]
    d_items = [x for x in drift if x["check"].startswith("D")]
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
    if d_items:
        print("\n(D) DELIVERABLE-KEY DRIFT — a required deliverable key is declared on one "
              "side of the contract and not the other:", file=sys.stderr)
        for d in d_items:
            print(f"  DRIFT {d['check']}: [{d['item']}] {d['detail']}", file=sys.stderr)
    if e:
        print("\n(E) PHASE-STRUCTURE DRIFT — a manifest phase is missing a required "
              "structural block (client_report; heartbeat_minutes on long_running "
              "phases E2 and heartbeat_minutes on EVERY phase E3):",
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
    _print_warnings(warnings, manifest)


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    explain = "--explain" in argv

    manifest = load_manifest()
    bd = parse_build_deck()
    ruleset_codes = parse_master_ruleset_section5()
    if len(ruleset_codes) < RULESET_MIN_SECTION5_CODES:
        refuse(f"Section-5 registry at {MASTER_RULESET} declares {len(ruleset_codes)} codes; "
               f"the canonical cluster registry declares {RULESET_MIN_SECTION5_CODES}. "
               f"provenance={RULESET_PROVENANCE}. Refusing to check drift against a truncated registry.")
    role_stems, sop_files = scan_roles_and_sops()

    drift = run_checks(manifest, bd, ruleset_codes, role_stems, sop_files)
    # (V) value-level drift — the cited NUMBER must equal the code constant.
    drift += value_checks(MANIFEST.read_text())
    # (W) warn-mode. SEPARATE list. Never merged into `drift` — see warn_checks().
    warnings = warn_checks(manifest)

    if as_json:
        # FIX-23(a) — expose the render-path vs library-only split so the canonical
        # door's GATE 3 can classify without re-parsing every drift item itself.
        render_path = [x for x in drift if x.get("class") != "A5/A6"]
        library_only = [x for x in drift if x.get("class") == "A5/A6"]
        print(json.dumps({
            "in_sync": not drift,
            "manifest_version": manifest["manifest_version"],
            "counts": {"phases": len(manifest["phases"]),
                       "autofails": len(manifest["autofails"]),
                       "roles": len(manifest["roles"])},
            "drift": drift,
            "drift_summary": {
                "total": len(drift),
                "render_path": len(render_path),
                "library_only": len(library_only),
            },
            "warnings": warnings,
            "warn_count": len(warnings),
        }, indent=2))
    else:
        report_human(drift, warnings, manifest, explain)

    sys.exit(4 if drift else 0)


if __name__ == "__main__":
    main()
