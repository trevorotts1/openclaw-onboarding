#!/usr/bin/env python3
"""
video_sync_check.py — MANIFEST <-> DRIVER <-> RULESET LOCKSTEP DETECTOR (Movie Producer).

================================================================================
SOP-LOCKED DEPARTMENT. This is the mechanism that makes the repo *know* — and
FAIL LOUD — when the enforcement code (executive_producer.py + video_build_check.py),
the SOP/role stack, and the MASTER-VIDEO ruleset drift apart. A rule not auto-failed
at a gate does not exist; lockstep is itself a gate. Mirrors the Presentations
sync_check.py contract.
================================================================================

WHAT IT DOES (zero third-party deps — stdlib json / re / ast / pathlib only):
It reconciles these on-disk inputs against the single source of truth
(VIDEO-PIPELINE-MANIFEST.json) in BOTH directions and exits 4 on any drift:

  1. VIDEO-PIPELINE-MANIFEST.json — the declared truth (phases / autofails / roles /
       deliverables_required).
  2. executive_producer.py + video_build_check.py — parsed two ways:
        * AST: the set of `def _chk_*` functions + enforcing functions
          (run_postflight_gate, kie_balance_preflight, check_phase_preconditions)
          and module-level constants (REQUIRED_BRIEF_FIELDS, NATIVE_PAID_PROVIDERS,
          DELIVERABLES_REQUIRED, ...) actually defined.
        * regex: every `AF-VID-...` string the source cites.
  3. MASTER-VIDEO-QC-AUTOFAIL-RULESET.md — Section 5 (MACHINE-CHECKABLE SUMMARY
        TABLE) parsed row-by-row to the canonical AF-code set.
  4. role-library/video/*.md + sops/*.md — the deployed video role + SOP file set,
        reconciled against the manifest owning_role + sop_refs.

DRIFT DIRECTIONS (both fail loud with the offending item + the fix verb):
  (A) STACK-AHEAD-OF-CODE — a manifest phase checker / AF code / role / SOP / Section-5
      row / deliverable key that has no matching symbol/file in the code/disk.
  (B) CODE-AHEAD-OF-STACK — an orphan `_chk_*` or `AF-VID-*` string in the code that
      the manifest does not declare.

EXIT CODES:
    0 — in sync.
    4 — drift (distinct from the driver's 2/3/4 so a caller can tell lockstep drift
        from a precondition/receipt/balance failure).
    2 — could not run (an input is missing/unparseable).

USAGE:
    python3 video_sync_check.py            # human report, exit 0 / 4
    python3 video_sync_check.py --json     # machine: {"in_sync":bool,"drift":[...]}
"""

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # .../47-movie-producer/scripts
SKILL_DIR = HERE.parent                                # .../47-movie-producer
EXEC_PRODUCER = HERE / "executive_producer.py"
BUILD_CHECK = HERE / "video_build_check.py"
TEST_PREFLIGHT = HERE / "test_video_preflight.py"

AF_RE = re.compile(r"AF-VID-[A-Z0-9]+(?:-[A-Z0-9]+)*")

# Deliverable key set lockstep (manifest deliverables_required <-> code DELIVERABLES_REQUIRED).
_EXPECTED_DELIVERABLE_KEYS = {"job_manifest", "render_receipt", "final_mp4"}


def _fatal(msg):
    print(f"FATAL (video_sync_check cannot run): {msg}", file=sys.stderr)
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


_REPO_ROOT = _find_repo_root(HERE)
_CLUSTER = (_REPO_ROOT / "universal-sops" / "video-pipeline-craft") if _REPO_ROOT else None


def _first_existing(paths):
    for p in paths:
        if p and p.exists():
            return p
    return paths[0]


MANIFEST = _first_existing([
    *([_CLUSTER / "VIDEO-PIPELINE-MANIFEST.json"] if _CLUSTER else []),
    SKILL_DIR / "sops" / "VIDEO-PIPELINE-MANIFEST.json",
    SKILL_DIR / "VIDEO-PIPELINE-MANIFEST.json",
])
MASTER_RULESET = _first_existing([
    *([_CLUSTER / "MASTER-VIDEO-QC-AUTOFAIL-RULESET.md"] if _CLUSTER else []),
    SKILL_DIR / "MASTER-VIDEO-QC-AUTOFAIL-RULESET.md",
])
# The video role-library + sops dirs (repo layout).
VIDEO_ROLE_DIR = (_REPO_ROOT / "23-ai-workforce-blueprint" / "templates"
                  / "role-library" / "video") if _REPO_ROOT else None
VIDEO_SOPS_DIR = (VIDEO_ROLE_DIR / "sops") if VIDEO_ROLE_DIR else None


# ---------------------------------------------------------------------------
# 1. Manifest
# ---------------------------------------------------------------------------
def load_manifest():
    if not MANIFEST.exists():
        _fatal(f"VIDEO-PIPELINE-MANIFEST.json not found (looked at {MANIFEST}).")
    try:
        m = json.loads(MANIFEST.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"VIDEO-PIPELINE-MANIFEST.json is not valid JSON: {exc}")
    for key in ("manifest_version", "phases", "autofails", "roles"):
        if key not in m:
            _fatal(f"VIDEO-PIPELINE-MANIFEST.json missing top-level key {key!r}.")
    if not isinstance(m["manifest_version"], int):
        _fatal("manifest_version must be an integer.")
    if "deliverables_required" not in m:
        _fatal("VIDEO-PIPELINE-MANIFEST.json requires a 'deliverables_required' key.")
    return m


# ---------------------------------------------------------------------------
# 2. Parse the enforcement code (both files) — AST + AF strings
# ---------------------------------------------------------------------------
def _parse_py(path: Path):
    if not path.exists():
        _fatal(f"{path.name} not found (looked at {path}).")
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        _fatal(f"{path.name} does not parse: {exc}")
    chk = set()
    consts = set()
    defined = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defined.add(node.name)
            if node.name.startswith("_chk_"):
                chk.add(node.name)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    consts.add(tgt.id)
                    defined.add(tgt.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defined.add(node.name)
    af = set(AF_RE.findall(src))
    deliv = _extract_deliverable_keys(tree)
    return {"chk": chk, "consts": consts, "defined": defined, "af": af,
            "deliverable_keys": deliv}


def _extract_deliverable_keys(tree):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "DELIVERABLES_REQUIRED":
                if not isinstance(node.value, ast.List):
                    return None
                keys = set()
                for elt in node.value.elts:
                    if not isinstance(elt, ast.Dict):
                        continue
                    for k, v in zip(elt.keys, elt.values):
                        if (isinstance(k, ast.Constant) and k.value == "key"
                                and isinstance(v, ast.Constant)):
                            keys.add(v.value)
                return keys if keys else None
    return None


def parse_code():
    ep = _parse_py(EXEC_PRODUCER)
    bc = _parse_py(BUILD_CHECK)
    return {
        "chk": ep["chk"] | bc["chk"],
        "defined": ep["defined"] | bc["defined"],
        "consts": ep["consts"] | bc["consts"],
        "af": ep["af"] | bc["af"],
        "deliverable_keys": bc["deliverable_keys"],
    }


# ---------------------------------------------------------------------------
# 3. MASTER ruleset Section 5 -> AF-code set
# ---------------------------------------------------------------------------
def parse_ruleset_section5():
    if not MASTER_RULESET.exists():
        _fatal(f"MASTER-VIDEO ruleset not found (looked at {MASTER_RULESET}).")
    lines = MASTER_RULESET.read_text().splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "MACHINE-CHECKABLE SUMMARY TABLE" in ln.upper():
            start = i
            break
    if start is None:
        _fatal("MASTER-VIDEO ruleset has no 'MACHINE-CHECKABLE SUMMARY TABLE' "
               "(Section 5). video_sync_check parses the AF registry from that table.")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    codes = set()
    for ln in lines[start:end]:
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        for code in AF_RE.findall(cells[0]):
            codes.add(code)
    if not codes:
        _fatal("Section 5 table parsed but no AF-VID-* codes found in column 1.")
    return codes


# ---------------------------------------------------------------------------
# 4. Role / SOP roster on disk
# ---------------------------------------------------------------------------
def scan_roles_and_sops():
    role_stems = set()
    sop_files = set()
    if VIDEO_ROLE_DIR and VIDEO_ROLE_DIR.is_dir():
        for p in VIDEO_ROLE_DIR.glob("*.md"):
            role_stems.add(p.stem)
    if VIDEO_SOPS_DIR and VIDEO_SOPS_DIR.is_dir():
        for p in VIDEO_SOPS_DIR.glob("*.md"):
            sop_files.add(p.name)
    return role_stems, sop_files


# ---------------------------------------------------------------------------
# DRIFT CHECKS
# ---------------------------------------------------------------------------
def run_checks(manifest, code, ruleset_codes, role_stems, sop_files):
    drift = []

    def add(check, item, detail):
        drift.append({"check": check, "item": item, "detail": detail})

    phases = manifest["phases"]
    autofails = manifest["autofails"]
    roles = manifest["roles"]

    manifest_af = {a["code"] for a in autofails}
    chk = code["chk"]
    defined = code["defined"]

    # checkers named by phases (primary + additional preflights)
    phase_checkers = set()
    for ph in phases:
        pf = ph.get("preflight")
        if pf and pf.get("checker"):
            phase_checkers.add(pf["checker"])
        for ap in ph.get("additional_preflights", []) or []:
            if ap.get("checker"):
                phase_checkers.add(ap["checker"])
    autofail_chk = {a.get("py_symbol") for a in autofails
                    if isinstance(a.get("py_symbol"), str)
                    and a["py_symbol"].startswith("_chk_")}
    referenced = phase_checkers | autofail_chk

    # ---- (A) STACK-AHEAD-OF-CODE ----
    # A1/A2: every required phase checker must be a defined _chk_ in the code.
    for ph in phases:
        pf = ph.get("preflight")
        if pf and pf.get("required"):
            c = pf.get("checker")
            if not c:
                add("A1", ph["id"], f"phase {ph['id']} preflight required but names no checker.")
            elif c not in chk:
                add("A2", c, f"phase {ph['id']} names checker {c!r}, not defined as a "
                            f"`def {c}` in executive_producer.py / video_build_check.py.")
        for ap in ph.get("additional_preflights", []) or []:
            if not ap.get("required"):
                continue
            c = ap.get("checker")
            if not c:
                add("A1", ph["id"], f"phase {ph['id']} additional_preflight names no checker.")
            elif c not in chk:
                add("A2", c, f"phase {ph['id']} additional_preflight names {c!r}, "
                            "not defined in the enforcement code.")

    # A3: every AF row enforced_by executive_producer -> py_symbol (+ secondaries) defined.
    for a in autofails:
        if a.get("enforced_by") == "executive_producer":
            sym = a.get("py_symbol")
            if not sym:
                add("A3", a["code"], f"AF {a['code']} enforced_by:executive_producer but no py_symbol.")
            elif sym not in defined:
                add("A3", a["code"], f"AF {a['code']} py_symbol {sym!r} not defined in the "
                                     "enforcement code.")
            for sec in a.get("secondary_py_symbols", []) or []:
                if sec not in defined:
                    add("A3", a["code"], f"AF {a['code']} secondary_py_symbol {sec!r} not "
                                         "defined in the enforcement code.")

    # A4: every Section-5 ruleset code must be in manifest.autofails.
    for c in sorted(ruleset_codes):
        if c not in manifest_af:
            add("A4", c, f"AF {c} is in the MASTER-VIDEO ruleset Section 5 but absent "
                         "from VIDEO-PIPELINE-MANIFEST.autofails.")

    # A4b: every manifest in_ruleset:true code must have a Section-5 row.
    for a in autofails:
        if a.get("in_ruleset") is True and a["code"] not in ruleset_codes:
            add("A4", a["code"], f"AF {a['code']} is manifest in_ruleset:true but has no "
                                 "row in the MASTER-VIDEO ruleset Section 5.")

    # A5: every shipped video role file stem referenced by the manifest must exist.
    manifest_role_ids = {r["id"] for r in roles}
    if role_stems:
        for ph in phases:
            owner = ph.get("owning_role")
            if owner and owner not in role_stems:
                add("A6", ph["id"], f"phase {ph['id']} owning_role {owner!r} has no "
                                    f"role-library file (video/{owner}.md).")
    # A5b: manifest roles that claim an owns_phase must be a real disk role (when the
    # disk roster is available — repo layout).
    if role_stems:
        for r in roles:
            if r.get("owns_phase") and r["id"] not in role_stems and r.get("owns_phase") not in (None,):
                # head-of-* conductor with owns_phase null is exempt; only flag real owners
                if r.get("owns_phase") not in (None, "null"):
                    add("A5", r["id"], f"manifest role {r['id']} owns a phase but has no "
                                       f"video/{r['id']}.md role-library file.")

    # A7: every phase sop_refs file (pre-'#') must exist in the sops dir.
    if sop_files:
        for ph in phases:
            for ref in ph.get("sop_refs", []) or []:
                fname = str(ref).split("#", 1)[0].strip()
                if fname and fname not in sop_files:
                    add("A7", f"{ph['id']}:{fname}", f"phase {ph['id']} references SOP "
                                                     f"{fname!r}, not present in the sops dir.")

    # ---- (B) CODE-AHEAD-OF-STACK ----
    # B1: orphan _chk_ in the code referenced by no manifest phase checker / autofail symbol.
    for fn in sorted(chk):
        if fn not in referenced:
            add("B1", fn, f"the enforcement code defines {fn} but no manifest phase "
                          "preflight.checker and no autofails[].py_symbol references it.")

    # B2: orphan AF-VID-* string cited in the code but absent from manifest.autofails.
    for c in sorted(code["af"]):
        if c not in manifest_af:
            add("B2", c, f"the enforcement code cites {c} but it is absent from "
                         "VIDEO-PIPELINE-MANIFEST.autofails.")

    # ---- (D) DELIVERABLE-SET DRIFT ----
    manifest_deliv = {d["key"] for d in manifest.get("deliverables_required", [])
                      if isinstance(d, dict) and "key" in d}
    code_deliv = code.get("deliverable_keys") or set()
    if manifest_deliv or code_deliv:
        for k in sorted(manifest_deliv - code_deliv):
            add("D1", k, f"deliverable key {k!r} is in the manifest deliverables_required "
                         "but absent from video_build_check.DELIVERABLES_REQUIRED.")
        for k in sorted(code_deliv - manifest_deliv):
            add("D2", k, f"deliverable key {k!r} is in video_build_check.DELIVERABLES_REQUIRED "
                         "but absent from the manifest deliverables_required.")

    return drift


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def report_human(drift, manifest):
    if not drift:
        print("=== video_sync_check: MOVIE-PRODUCER MANIFEST <-> CODE <-> RULESET LOCKSTEP ===")
        print(f"manifest_version: {manifest['manifest_version']}")
        print(f"phases: {len(manifest['phases'])}  autofails: {len(manifest['autofails'])}  "
              f"roles: {len(manifest['roles'])}")
        print("IN SYNC — executive_producer.py + video_build_check.py, the MASTER-VIDEO "
              "ruleset Section-5 table, the role roster, and the SOP set all match "
              "VIDEO-PIPELINE-MANIFEST.json.")
        return
    a = [d for d in drift if d["check"].startswith("A")]
    b = [d for d in drift if d["check"].startswith("B")]
    dd = [d for d in drift if d["check"].startswith("D")]
    print("=== video_sync_check: DRIFT DETECTED — LOCKSTEP BROKEN (AF-VID-SYNC) ===",
          file=sys.stderr)
    for label, group in (("(A) STACK-AHEAD-OF-CODE", a),
                         ("(B) CODE-AHEAD-OF-STACK", b),
                         ("(D) DELIVERABLE-SET DRIFT", dd)):
        if group:
            print(f"\n{label}:", file=sys.stderr)
            for d in group:
                print(f"  DRIFT {d['check']}: [{d['item']}] {d['detail']}", file=sys.stderr)
    print(f"\n{len(drift)} drift item(s). Any change to a Movie-Producer SOP/role/gate "
          "MUST update VIDEO-PIPELINE-MANIFEST.json (+bump manifest_version), the "
          "enforcement code, the MASTER-VIDEO ruleset, and a test.", file=sys.stderr)


def main():
    as_json = "--json" in sys.argv[1:]
    manifest = load_manifest()
    code = parse_code()
    ruleset_codes = parse_ruleset_section5()
    role_stems, sop_files = scan_roles_and_sops()
    drift = run_checks(manifest, code, ruleset_codes, role_stems, sop_files)

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
        report_human(drift, manifest)
    sys.exit(4 if drift else 0)


if __name__ == "__main__":
    main()
