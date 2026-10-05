#!/usr/bin/env python3
"""repair-directors-doctrine.py -- bring an EXISTING box up to the director standard.

Installs since v25.4.0 never ship a headless department or a doctrine-less
director. Boxes built before that can have all three defects. This script
repairs them on a live box, additively:

  1. DIRECTOR. Every department without a director/head role gets one:
     the department's own library director template when the library has one,
     otherwise the generic templates/role-library/_director-scaffold.md.
     Same fill path the installer uses (create_role_workspaces), so a repaired
     director is identical to a freshly built one.
  2. DOCTRINE. Every existing director/head playbook that lacks the
     persistent-director / ephemeral-worker doctrine and the chain of command
     gets one marker-guarded block APPENDED. Existing text is never edited:
     the old bytes stay a byte-for-byte prefix of the new file. Playbooks that
     already carry the doctrine (marker or headings) are never touched, so a
     second run is a no-op.
  3. AI CEO PLAYBOOK. If the box has no substantive AI CEO playbook, one is
     created from the library master-orchestrator template at
     departments/ai-ceo/01-ai-ceo-<name>/how-to.md.

Every name comes from the box's own company-config.json (aiCeoName /
ai_ceo_name / aiCEOName, then agentName, else the neutral "AI CEO"); the
owner and company names flow through the same token fill the installer uses.
No name is hardcoded here.

Never touched: openclaw.json, any model or credential setting, any existing
how-to.md content, ROSTER.md. A director or head playbook that is a placeholder
or thinner than the 3072-byte floor is skipped and reported: doctrine appended
to a stub would hide the stub from the placeholder repair.

Usage:
  repair-directors-doctrine.py [--dry-run] [--json]
                               [--departments-dir DIR] [--workspace-dir DIR]
                               [--config FILE]
Default writes. --dry-run reads and reports only. Re-running is safe.

EXIT CODES:
  0 = done (or dry-run report produced); nothing failed
  1 = no departments directory or no role library found
  2 = one or more items failed (details in the report)
"""
import argparse
import contextlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # scripts/ holds create_role_workspaces

import create_role_workspaces as crw  # noqa: E402

MIN_BYTES = 3072  # same substance floor the installer enforces
CEO_DEPT = "ai-ceo"
CEO_NAME_KEYS = ("aiCeoName", "ai_ceo_name", "aiCEOName", "agentName")
PLACEHOLDER_MARKERS = (
    "PENDING - FILL FROM LIBRARY",
    "PENDING FILL FROM LIBRARY",
    "PENDING — FILL FROM LIBRARY",
    "how-to.md (stub)",
    "[ROUTED — WORK HANDLED BY GENERAL-TASK]",
)
MARKER = "<!-- DIRECTOR-DOCTRINE:v1 BEGIN -->"
MARKER_END = "<!-- DIRECTOR-DOCTRINE:v1 END -->"

# Same text as section 20 of the library director templates (the canonical
# doctrine). {{AI_CEO_NAME}} is replaced with the box's own AI CEO name.
DOCTRINE = MARKER + """
## Director Operating Doctrine — Persistent Director, Ephemeral Workers

This section is structural. It describes how every director in every install
operates, regardless of department. It is not department-specific and must not
be weakened or removed.

### You persist; workers do not

You, the director, are **persistent**: always alive, holding this department's
memory across tasks. Workers are **ephemeral**: spawned per task, terminated
when done. A worker is a process running a program — the role's SOP is the
program.

### A worker becomes the role ONLY by executing its SOP step by step

A spawned sub-agent is not a specialist by itself. It becomes the role **only**
by loading that role's `how-to.md` (and the SOP files it indexes) and executing
the procedure literally, in order, without improvisation. Never dispatch a
worker without pointing it at its SOP. Never accept "I improvised" as a result —
a task with no covering SOP is a gap: route the immediate work to the
general-task department and trigger the SOP-Writer to close the gap permanently.

### Dispatch → report → terminate

Every unit of work follows one lifecycle: you decompose the task, spawn one
ephemeral worker per unit (each loaded with its role's SOP), collect and
quality-check the reports against the role's Definition of Done, terminate the
workers, write what matters into department memory, and report up to
{{AI_CEO_NAME}}. Their memory dies with them; the department's memory is yours.

### Chain of command — never skip a level

Owner → {{AI_CEO_NAME}} (AI CEO) → directors → ephemeral workers. {{AI_CEO_NAME}}
talks only to directors, never to workers. You talk only to {{AI_CEO_NAME}} and
your own workers — never to another department's workers, never past the CEO.
Reports flow back up the same chain: worker → you → {{AI_CEO_NAME}} → owner.
""" + MARKER_END + "\n"

_HEAD_EPHEMERAL = re.compile(r"ephemeral", re.I)
_HEAD_CHAIN = re.compile(r"chain[\s-]+(of[\s-]+)?command", re.I)
_NN = re.compile(r"^(\d+)-(.+)$")
_DIRECTOR_SLUG = re.compile(r"(^|-)director(-|$)|(^|-)head-of-")

def log(msg):
    print(f"[REPAIR-DIRECTORS] {msg}", file=sys.stderr)

# --- names ------------------------------------------------------------------

def load_config(paths):
    """First non-missing value per key across the candidate config files."""
    cfg = {}
    for p in paths:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            for k, v in data.items():
                cfg.setdefault(k, v)
    return cfg

def resolve_ceo_name(cfg):
    for key in CEO_NAME_KEYS:
        v = cfg.get(key)
        if isinstance(v, str) and v.strip():
            return re.sub(r"[{}\r\n\t]", "", v).strip() or "AI CEO", key
    return "AI CEO", "default"

# --- classification ---------------------------------------------------------

def is_placeholder_head(head):
    return any(m in head for m in PLACEHOLDER_MARKERS)

def is_substantive(path):
    try:
        if not path.is_file():
            return False
        with open(path, "rb") as fh:
            head = fh.read(600).decode("utf-8", "replace")
        return path.stat().st_size >= MIN_BYTES and not is_placeholder_head(head)
    except OSError:
        return False

def is_director_folder(name):
    m = _NN.match(name)
    slug = (m.group(2) if m else name).lower()
    if m and int(m.group(1)) == 0:
        return True
    return bool(_DIRECTOR_SLUG.search(slug))

def role_folders(dept):
    """Role folders of a department (flat NN-slug/ layout plus roles/ nesting)."""
    skip = {s.lower() for s in getattr(crw, "_ROSTER_SKIP_FOLDERS", set())}
    out = []
    parents = [dept] + ([dept / "roles"] if (dept / "roles").is_dir() else [])
    for parent in parents:
        for e in sorted(parent.iterdir()):
            if (not e.is_dir() or e.is_symlink() or e.name.startswith((".", "_"))
                    or e.name.lower() in skip or ".bak" in e.name):
                continue
            if any((e / f).exists() for f in ("how-to.md", "IDENTITY.md", "00-START-HERE.md")):
                out.append(e)
    return out

def has_doctrine(text):
    if MARKER in text:
        return True
    heads = [l for l in text.splitlines() if l.lstrip().startswith("#")]
    return (any(_HEAD_EPHEMERAL.search(h) for h in heads)
            and any(_HEAD_CHAIN.search(h) for h in heads))

# --- writes (all go through here so dry-run is one flag) ---------------------

def atomic_write_bytes(path, data):
    tmp = path.with_name(f".{path.name}.doctrine-tmp-{os.getpid()}")
    try:
        tmp.write_bytes(data)
        shutil.copymode(path, tmp) if path.exists() else None
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()

def append_doctrine(how_to, ceo, dry, rep, rel):
    if how_to.is_symlink():
        rep["doctrine_skipped"].append({"path": rel, "reason": "how-to.md is a symlink"})
        return
    if not how_to.is_file():
        rep["director_howto_missing"].append(rel)
        return
    data = how_to.read_bytes()
    if len(data) < MIN_BYTES or is_placeholder_head(data[:600].decode("utf-8", "replace")):
        rep["doctrine_skipped"].append(
            {"path": rel, "reason": "placeholder or thinner than 3072 bytes; fill it first"})
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        rep["doctrine_skipped"].append({"path": rel, "reason": "not valid UTF-8"})
        return
    if has_doctrine(text):
        rep["doctrine_already_present"] += 1
        return
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    block = DOCTRINE.replace("{{AI_CEO_NAME}}", ceo)
    if not dry:
        atomic_write_bytes(how_to, data + (sep + block).encode("utf-8"))
    rep["doctrine_appended"].append(rel)

# --- director creation -------------------------------------------------------

def build_director_how_to(dept):
    """(text, source) for a new director playbook, or raise. Library first."""
    dept_slug = dept.name.lower()
    dept_name = dept.name.replace("-dept", "").replace("-", " ").title()
    role_name = f"Director of {dept_name}"
    slug = crw.slugify(dept_slug)
    for key in (f"director-of-{slug}", "director", f"head-of-{slug}"):
        try:
            path, entry = crw.library_lookup(key, dept_slug)
        except Exception:  # noqa: BLE001 -- lookup must never abort the repair
            path, entry = None, None
        if path and entry:
            filled = crw.try_library_fill(role_name, dept, False, lib_key=entry["slug"])
            if filled:
                return filled, f"library:{entry['dept']}/{entry['slug']}"
            break
    filled = crw._fill_director_scaffold(role_name, dept_name, False)  # ponytail: private helper, same module family; promote if a third caller appears
    if filled:
        return filled, "scaffold"
    raise RuntimeError("no library director template and the generic scaffold could not be filled")

def create_director(dept, workspace, dry, rep):
    dept_name = dept.name.replace("-dept", "").replace("-", " ").title()
    text, source = build_director_how_to(dept)
    if len(text.encode("utf-8")) < MIN_BYTES or "{{AI_CEO_NAME}}" in text:
        raise RuntimeError("filled director playbook failed the substance check")
    folder = dept / f"00-director-of-{crw.slugify(dept.name.lower())}"
    rep["directors_created"].append({"department": dept.name, "folder": folder.name,
                                     "source": source})
    if dry:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    how_to = folder / "how-to.md"
    if not how_to.exists():
        how_to.write_text(text, encoding="utf-8")
    # Identity files, SOP/ index and the shared TOOLS.md/USER.md copies, exactly
    # as the installer lays them down. how-to.md already exists so it is kept.
    crw.augment_role_folder(folder, workspace, role_metadata={"name": f"Director of {dept_name}"})
    return how_to

# --- AI CEO playbook ---------------------------------------------------------

def ceo_playbook_candidates(workspace, depts, company_dir):
    cands = []
    for d in depts.iterdir():
        if d.is_dir() and d.name.lower() == CEO_DEPT:
            cands += sorted(d.glob("*/how-to.md"))
    cands += [workspace / "master-orchestrator" / "how-to.md",
              depts / "master-orchestrator" / "master-orchestrator" / "how-to.md"]
    if company_dir:
        cands.append(Path(company_dir) / "master-orchestrator" / "how-to.md")
    return cands

def ensure_ceo_playbook(workspace, depts, company_dir, ceo, dry, rep):
    if any(is_substantive(p) for p in ceo_playbook_candidates(workspace, depts, company_dir)):
        rep["ceo_playbook"] = "exists"
        return
    ai_dir = next((d for d in depts.iterdir() if d.is_dir() and d.name.lower() == CEO_DEPT),
                  depts / CEO_DEPT)
    slug = crw.slugify(ceo)
    folder = ai_dir / ("01-ai-ceo" if slug in ("", "ai-ceo") else f"01-ai-ceo-{slug}")
    target = folder / "how-to.md"
    if target.exists():
        rep["ceo_playbook"] = "placeholder-in-place: fill it with repair-placeholder-sops.py"
        return
    # ponytail: try_library_fill only reads the dept path's NAME, so a bare Path
    # resolves the master-orchestrator template without touching disk.
    filled = crw.try_library_fill("Master Orchestrator", Path("master-orchestrator"), True,
                                  lib_key="master-orchestrator")
    if not filled or "{{AI_CEO_NAME}}" in filled:
        raise RuntimeError("library master-orchestrator template missing or unfillable")
    rep["ceo_playbook"] = "would-create" if dry else "created"
    rep["ceo_playbook_path"] = f"{CEO_DEPT}/{folder.name}/how-to.md"
    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
        target.write_text(filled, encoding="utf-8")

# --- main --------------------------------------------------------------------

def run(a):
    rep = {"dry_run": a.dry_run, "departments_scanned": 0, "directors_created": [],
           "directors_existing": 0, "doctrine_appended": [], "doctrine_already_present": 0,
           "doctrine_skipped": [], "director_howto_missing": [], "skipped_empty": [],
           "ceo_playbook": "unknown", "errors": []}
    company_dir = None
    if a.departments_dir:
        depts = Path(a.departments_dir)
        workspace = Path(a.workspace_dir) if a.workspace_dir else depts.parent
        cfg_paths = [a.config] if a.config else [workspace / "company-config.json"]
    else:
        from _qc_paths import live_departments_dir, platform_workspace
        workspace = Path(a.workspace_dir) if a.workspace_dir else platform_workspace()
        paths = {}
        try:
            paths = crw.get_openclaw_paths()
        except (Exception, SystemExit):  # noqa: BLE001 -- fall back to workspace layout
            pass
        company_dir = paths.get("company_dir")
        depts = live_departments_dir()
        if not depts.is_dir() and company_dir:
            depts = Path(company_dir) / "departments"
        cfg_paths = [a.config] if a.config else [paths.get("company_config"),
                                                  workspace / "company-config.json"]
    if not depts.is_dir():
        log(f"departments directory not found: {depts}")
        return 1, rep
    cfg = load_config([p for p in cfg_paths if p])
    ceo, rep["ai_ceo_name_source"] = resolve_ceo_name(cfg)
    cfg["aiCeoName"] = ceo
    # ponytail: the installer's token fill reads its own global config loader;
    # point it at the config resolved above so names agree. Fine for a one-shot CLI.
    crw._load_company_config = lambda: cfg
    rep["departments_dir"] = str(depts)

    for dept in sorted(depts.iterdir(), key=lambda p: p.name.lower()):
        if (not dept.is_dir() or dept.is_symlink() or dept.name.startswith((".", "_"))
                or ".bak" in dept.name):
            continue
        rep["departments_scanned"] += 1
        try:
            roles = role_folders(dept)
            directors = [r for r in roles if is_director_folder(r.name)]
            if not directors and dept.name.lower() != CEO_DEPT:
                if not roles:
                    rep["skipped_empty"].append(dept.name)
                    continue
                new = create_director(dept, workspace, a.dry_run, rep)
                if new is not None:
                    directors = [new.parent]
            else:
                rep["directors_existing"] += len(directors)
            for d in directors:
                if not a.dry_run or d.exists():
                    append_doctrine(d / "how-to.md", ceo, a.dry_run, rep,
                                    f"{dept.name}/{d.name}/how-to.md")
        except Exception as e:  # noqa: BLE001 -- one bad department must not stop the rest
            rep["errors"].append({"department": dept.name, "error": str(e)})
    try:
        ensure_ceo_playbook(workspace, depts, company_dir, ceo, a.dry_run, rep)
    except Exception as e:  # noqa: BLE001
        rep["ceo_playbook"] = "error"
        rep["errors"].append({"department": CEO_DEPT, "error": str(e)})
    return (2 if rep["errors"] else 0), rep

def print_report(rep):
    tag = " (dry run: nothing written)" if rep["dry_run"] else ""
    print(f"Directors and doctrine repair{tag}")
    print(f"  Departments scanned:            {rep['departments_scanned']}")
    print(f"  Directors already present:      {rep['directors_existing']}")
    print(f"  Directors created:              {len(rep['directors_created'])}")
    for d in rep["directors_created"]:
        print(f"      {d['department']}/{d['folder']}  ({d['source']})")
    print(f"  Doctrine appended:              {len(rep['doctrine_appended'])}")
    print(f"  Doctrine already present:       {rep['doctrine_already_present']}")
    print(f"  Skipped (placeholder or thin):  {len(rep['doctrine_skipped'])}")
    print(f"  Director folders lacking how-to: {len(rep['director_howto_missing'])}")
    print(f"  Empty departments skipped:      {len(rep['skipped_empty'])}")
    print(f"  AI CEO playbook:                {rep['ceo_playbook']}")
    for e in rep["errors"]:
        print(f"  ERROR {e['department']}: {e['error']}")

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--departments-dir")
    ap.add_argument("--workspace-dir")
    ap.add_argument("--config", help="company-config.json to read names from")
    a = ap.parse_args(argv)
    # The installer helpers print progress lines; keep stdout clean for --json.
    with contextlib.redirect_stdout(sys.stderr):
        rc, rep = run(a)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
    return rc

if __name__ == "__main__":
    sys.exit(main())
