#!/usr/bin/env python3
"""reconcile-role-floor.py - bring an existing departments tree up to the role-library floor.

Older interview builds named role folders from the suggested-roles headers
("01-director-of-crm-full-time-permanent") and built only the roles the roster
listed, so the tree sits below the floor the prover enforces (no healer, no
devil's advocate, no SOP writer). This repairs such a tree in place:

  1. RENAME every role folder whose name resolves to a role-library slug but is
     not that slug: "01-director-of-crm-full-time-permanent" -> "01-director-of-crm".
     A rename moves the folder whole, so every how-to and SOP already written is
     kept byte-for-byte. A folder is NOT renamed (reported as a conflict) when a
     folder for the same library role already exists, or when openclaw.json
     references its path.
  2. FILL the library roles still missing, through floor-fill-driver.py (the
     supported, fill-missing-only materializer: library content, never
     overwrites, industry gate for absent departments).
  3. With --add-floor-departments, also fill the standard-floor departments the
     tree lacks (department-floor.py: mandatory + universal primaries, minus the
     owner's declines). Library departments outside that floor are never added.

Dry run by default. --apply renames and fills. Idempotent: a second run finds
nothing to rename and nothing missing.

Usage:
  python3 reconcile-role-floor.py --departments <company>/departments
  python3 reconcile-role-floor.py --departments <company>/departments --add-floor-departments --apply
Exit codes: 0 clean/applied, 2 dry-run changes pending, 3 floor-fill left gaps, 1 error.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import create_role_workspaces as crw  # noqa: E402

INDEX = SKILL_DIR / "templates" / "role-library" / "_index.json"
NN = re.compile(r"^(\d+)[-_](.+)$")


def key(slug):
    """The floor prover's role key: no NN- prefix, '--' folded to '-'."""
    m = NN.match(slug)
    return re.sub(r"-{2,}", "-", (m.group(2) if m else slug).lower())


def library_roles(dept):
    lib = crw.normalize_dept(dept)
    roles = json.loads(INDEX.read_text()).get("roles", [])
    return sorted({e["slug"] for e in roles if (e.get("dept") or "").lower() == lib and e.get("slug")})


def config_text():
    for p in (Path("/data/.openclaw/openclaw.json"), Path.home() / ".openclaw" / "openclaw.json"):
        if p.is_file():
            return p.read_text(errors="replace")
    return ""


def plan_renames(dept_dir, lib, cfg):
    lib_keys = {key(s) for s in lib}
    folders = [p for p in dept_dir.iterdir() if p.is_dir()]
    taken = {key(p.name) for p in folders}
    renames, conflicts = [], []
    for p in sorted(folders):
        m = NN.match(p.name)
        if not m or key(p.name) in lib_keys:
            continue
        _, entry = crw.library_lookup(m.group(2), dept_dir.name)
        if not entry or key(entry.get("slug", "")) not in lib_keys:
            continue
        target = dept_dir / f"{m.group(1)}-{entry['slug']}"
        if key(entry["slug"]) in taken:
            conflicts.append((p.name, target.name, "a folder for this library role already exists"))
        elif str(p) in cfg:
            conflicts.append((p.name, target.name, "openclaw.json references this path"))
        else:
            renames.append((p, target))
            taken.add(key(entry["slug"]))
    return renames, conflicts


def floor_departments(departments):
    spec = importlib.util.spec_from_file_location("department_floor", SCRIPT_DIR / "department-floor.py")
    df = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(df)
    v = df.evaluate_floor(departments_dir=departments)
    return sorted(set(v.get("missing_mandatory", [])) | set(v.get("missing_universal_primary", [])))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--departments", required=True, help="the company's departments/ directory")
    ap.add_argument("--add-floor-departments", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    departments = Path(a.departments).expanduser().resolve()
    if not departments.is_dir():
        print(f"ERROR: {departments} is not a directory", file=sys.stderr)
        return 1
    cfg = config_text()
    report = {"apply": a.apply, "departments": str(departments), "renamed": {}, "conflicts": {}, "gap": {}}
    gap = {}
    for dept_dir in sorted(p for p in departments.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        lib = library_roles(dept_dir.name)
        if not lib:
            continue
        renames, conflicts = plan_renames(dept_dir, lib, cfg)
        if renames:
            report["renamed"][dept_dir.name] = [f"{s.name} -> {t.name}" for s, t in renames]
        if conflicts:
            report["conflicts"][dept_dir.name] = [f"{s} -> {t}: {why}" for s, t, why in conflicts]
        if a.apply:
            for src, dst in renames:
                src.rename(dst)
        present = {key(p.name) for p in dept_dir.iterdir() if p.is_dir()}
        present |= {key(dst.name) for _, dst in renames}
        missing = [s for s in lib if key(s) not in present]
        if missing:
            gap[dept_dir.name] = {"kind": "roster", "missing_roles": missing}
    if a.add_floor_departments:
        for dept in floor_departments(departments):
            if crw.resolve_dept_dir(departments, dept) is None and library_roles(dept):
                gap[dept] = {"kind": "roster", "missing_roles": library_roles(dept)}
    report["gap"] = {d: len(v["missing_roles"]) for d, v in gap.items()}
    print(json.dumps(report, indent=1))

    if not gap:
        return 0 if (a.apply or not report["renamed"]) else 2
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(gap, f)
    cmd = [sys.executable, str(SCRIPT_DIR / "floor-fill-driver.py"), "--gap-file", f.name,
           "--workspace", str(departments)] + (["--apply"] if a.apply else [])
    rc = subprocess.run(cmd).returncode
    Path(f.name).unlink(missing_ok=True)
    if rc:
        return rc
    return 0 if a.apply else 2


if __name__ == "__main__":
    sys.exit(main())
