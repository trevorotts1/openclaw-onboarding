#!/usr/bin/env python3
"""ensure-general-task-dept.py — make sure THIS box has a working general-task department.

general-task is the catch-all every unroutable task lands in. If it is missing,
or its role playbooks are empty / thin / installer placeholders, routed work has
nowhere real to go. This script installs it from the shipped role library:

  * the department folder          departments/general-task/
  * the department-level files     IDENTITY / SOUL / TOOLS / how-to-use-this-department, ROSTER
  * every general-task role        NN-<slug>/ with a real how-to.md (own playbook),
                                   IDENTITY / SOUL / MEMORY / HEARTBEAT, SOP/ index, TOOLS / USER

Names (company, owner, AI CEO) come from the box's own company config through the
installer's own token filler (create_role_workspaces.fill_tokens). No model call,
no network, no hardcoded model or provider.

Rules:
  * A role whose how-to.md is real (>= 3072 bytes, no placeholder text) is NEVER
    touched. Only a missing role folder or a placeholder / thin / empty how-to.md
    is written, atomically (temp file + rename).
  * Idempotent: a second run finds everything present and changes nothing.
  * Never touches openclaw.json, never registers agents, never talks to the
    Command Center. Agent registration stays with materialize-dept-agents.sh.
  * A role the library has no usable template for is reported, never guessed.

Usage:
  ensure-general-task-dept.py [--workspace DIR] [--departments-dir DIR]
                              [--skill-dir DIR] [--company-config FILE]
                              [--dry-run] [--json]

  --workspace        OpenClaw workspace. Default: the platform workspace.
  --departments-dir  Default: the live departments tree (build-state companyRoot
                     first, else <workspace>/departments; same rule as _qc_paths).
  --skill-dir        23-ai-workforce-blueprint dir holding templates/role-library.
                     Default: $ROLE_LIBRARY_PATH if valid, else this script's own skill.
  --company-config   company-config.json to take names from (sets
                     OPENCLAW_COMPANY_CONFIG for the filler).
  --dry-run          Report what would change; write nothing.
  --json             Machine-readable report on stdout.

EXIT CODES:
  0 = general-task is present with at least one real playbook (installed, repaired
      or already fine; dry-run: the plan was produced)
  1 = cannot run (no role library, departments tree unresolvable, unexpected error)
  3 = ran, but no real general-task playbook exists afterwards
"""
import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path

SKILL_DEFAULT = Path(__file__).resolve().parents[2]
DEPT = "general-task"
# Same order as suggested-roles/general-task-suggested-roles.md (folders 00..04);
# every other general-task library role follows alphabetically.
MANDATORY = ["head-of-general-task", "generalist-operator", "triage-classifier",
             "qc-specialist-general-task", "sop-writer"]
MIN_BYTES = 3072   # = LIBRARY_MIN_BYTES / HOW_TO_MIN_BYTES elsewhere in the repo
HEAD = 600         # placeholder text counts only in the first 600 bytes (a real playbook may QUOTE it)
SIG = re.compile(
    r"PENDING\W{0,4}FILL FROM LIBRARY"
    r"|how-to\.md \(stub\)"
    r"|to be personalized based on research"
    r"|\[\s*step\s+\d+\s*[-–—]\s*to be personalized"
    r"|\[ROUTED\W{1,6}WORK HANDLED BY GENERAL-TASK\]",
    re.IGNORECASE)


def bad_reason(p):
    """Why this how-to.md is not a real playbook, or None when it is real."""
    try:
        size = p.stat().st_size
        with open(str(p), "rb") as f:
            head = f.read(HEAD).decode("utf-8", "ignore")
    except OSError:
        return "missing" if not p.exists() else "unreadable"
    if size == 0 or not head.strip():
        return "empty"
    if SIG.search(head):
        return "placeholder text"
    if size < MIN_BYTES:
        return "thin (%d bytes)" % size
    return None


def atomic_write(p, text):
    tmp = p.with_name(".%s.tmp-%d" % (p.name, os.getpid()))
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def library_roles(skill):
    """General-task roles from the library index, mandatory five first."""
    index = json.loads((skill / "templates" / "role-library" / "_index.json").read_text(encoding="utf-8"))
    roles = {r["slug"]: r for r in index.get("roles", []) if r.get("dept") == DEPT and r.get("slug")}
    ordered = [s for s in MANDATORY if s in roles] + sorted(s for s in roles if s not in MANDATORY)
    return [(n, roles[s]) for n, s in enumerate(ordered)]


def load_installer(skill):
    sys.path.insert(0, str(skill / "scripts"))
    import create_role_workspaces as crw  # noqa: PLC0415
    import _qc_paths  # noqa: PLC0415
    return crw, _qc_paths


def fill(crw, entry):
    """Token-filled library playbook for one role, or None (no match / below the floor)."""
    return crw.try_library_fill(entry.get("title") or entry["slug"], Path(DEPT), False, lib_key=entry["slug"])


def run(a):
    env_lib = os.environ.get("ROLE_LIBRARY_PATH", "").strip()
    skill = Path(a.skill_dir or (env_lib if env_lib and (Path(env_lib) / "templates/role-library/_index.json").is_file()
                                 else SKILL_DEFAULT))
    if not (skill / "templates" / "role-library" / "_index.json").is_file():
        raise RuntimeError("no role library at %s" % skill)
    os.environ["ROLE_LIBRARY_PATH"] = str(skill)
    if a.company_config:
        os.environ["OPENCLAW_COMPANY_CONFIG"] = a.company_config
    crw, qc = load_installer(skill)
    ws = Path(a.workspace) if a.workspace else qc.platform_workspace()
    dd = Path(a.departments_dir) if a.departments_dir else qc.departments_root_for(ws)
    plan = library_roles(skill)
    if not plan:
        raise RuntimeError("the role library has no %s roles" % DEPT)

    existing = crw.resolve_dept_dir(dd, DEPT) if dd.is_dir() else None
    dept = existing or (dd / DEPT)
    rep = {"workspace": str(ws), "departments_dir": str(dd), "department_dir": str(dept), "dry_run": a.dry_run,
           "department_created": existing is None, "roles": [], "dept_files": [], "real_playbooks": 0, "errors": 0}
    if not a.dry_run:
        dept.mkdir(parents=True, exist_ok=True)

    changed = existing is None
    for number, entry in plan:
        slug = entry["slug"]
        folders = {re.sub(r"^\d+-", "", d.name): d for d in dept.iterdir() if d.is_dir()} if dept.is_dir() else {}
        item = {"slug": slug, "folder": None, "action": None, "reason": None}
        rep["roles"].append(item)
        folder = folders.get(slug)
        if folder is not None:
            item["folder"] = folder.name
            why = bad_reason(folder / "how-to.md")
            if why is None:
                item["action"] = "kept"
                continue
            item.update(action="would-refill" if a.dry_run else "refilled", reason=why)
        else:
            item.update(folder="%02d-%s" % (number, slug), action="would-create" if a.dry_run else "created")
        if a.dry_run:
            changed = True
            continue
        text = fill(crw, entry)
        if text is None:
            item.update(action="unavailable", reason="no usable library template (missing or below %d bytes)" % MIN_BYTES)
            rep["errors"] += 1
            continue
        if folder is None:
            crw.create_role_workspace(dept, entry.get("title") or slug, ws,
                                      role_metadata={"slug": slug, "number": number})
            folder = dept / item["folder"]
        if bad_reason(folder / "how-to.md") is not None:   # a routing notice from a non-standard folder name
            atomic_write(folder / "how-to.md", text)
        changed = True

    files = crw.scaffold_department(dept, DEPT, dry_run=a.dry_run)["files"] if (dept.is_dir() or not a.dry_run) else []
    rep["dept_files"] = files
    if files:
        changed = True
    if not a.dry_run:
        if changed or not (dept / "ROSTER.md").exists():
            crw.regenerate_department_roster(dept)
        rep["real_playbooks"] = sum(1 for d in dept.iterdir()
                                    if d.is_dir() and bad_reason(d / "how-to.md") is None)
    rep["changed"] = changed
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ensure-general-task-dept.py")
    for flag in ("--workspace", "--departments-dir", "--skill-dir", "--company-config"):
        ap.add_argument(flag)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        # the installer helpers print progress lines; keep stdout for this script's own report
        with contextlib.redirect_stdout(sys.stderr):
            rep = run(a)
    except (RuntimeError, OSError, ValueError, KeyError, ImportError, SystemExit) as e:
        print("[ensure-general-task-dept] ERROR: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print("[ensure-general-task-dept] department: %s%s" % (rep["department_dir"], " (new)" if rep["department_created"] else ""))
        for r in rep["roles"]:
            print("  %-13s %s%s" % (r["action"], r["folder"] or r["slug"], " - " + r["reason"] if r["reason"] else ""))
        if rep["dept_files"]:
            print("  department files: %s" % ", ".join(rep["dept_files"]))
        print("[ensure-general-task-dept] RESULT: %s" % (
            "DRY-RUN (nothing written)" if a.dry_run else
            ("CHANGED" if rep["changed"] else "NO CHANGE") + " - %d real playbook(s)" % rep["real_playbooks"]))
    if a.dry_run:
        return 0
    return 0 if rep["real_playbooks"] > 0 and rep["errors"] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
