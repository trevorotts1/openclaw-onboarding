#!/usr/bin/env python3
"""
materialize-missing-departments.py — P2-06 (c)2: THE FLOOR-WIPE FIX, live remediation.

ROOT CAUSE (P2-06 (b), already fixed at the BUILD-TIME layer): when
department-naming-map.json was unreadable, the build used to SILENTLY drop
to 22 departments (losing the 6 universal-primary). department-floor.py /
build-workforce.py now fail CLOSED (unreadable map -> the full 28-department
floor is still enforced via HARDCODED_MANDATORY + HARDCODED_UNIVERSAL_PRIMARY,
never a silent short list). That fix stops a NEW build from ever going short.

This script closes the RESIDUE: a box that was BUILT before the fix landed
(or otherwise "hit the wipe") is still missing whole departments TODAY, and
nothing in the update path re-materializes a whole missing department (only
missing ROLES/SOPS inside an EXISTING department — see
migrate-existing-workforce.sh Step 2b / floor-fill-driver.py v16.0.2). A
department that is entirely absent from disk was invisible to that path
because make-gap-from-staleness.py deliberately drops "dept"-kind items
(see tests/unit/floor-fill-gap.test.sh: "STALE / dept items must be dropped").

This script is the whole-department remediation floor-fill-driver.py never
got wired for:

  1. department_floor.evaluate_floor(departments_dir) -> the LIVE HARD-floor
     verdict (respects client declines; never re-adds a declined dept).
  2. For each dept the verdict reports MISSING (missing_mandatory +
     missing_universal_primary), resolve its role-library folder via
     create_role_workspaces.normalize_dept() and enumerate every shipped
     role .md file there -> the FULL roster (the dept does not exist on disk
     at all, so every library role for it is "missing").
  3. Write that as a gap-map in floor-fill-driver.py's own schema and invoke
     floor-fill-driver.py (subprocess, --apply) — REUSING the already-shipped,
     already-QC'd v16.0.2 additive / skip-existing / no-clobber materializer
     instead of re-implementing folder creation here.
  4. Re-run evaluate_floor() and report the before/after verdict.

SAFETY CONTRACT (inherited from floor-fill-driver.py, not reimplemented):
  - additive-only: only CREATES departments/roles absent from disk. A
    department already present (under its canonical id OR any known variant
    slug — department_floor._present()) is never touched: evaluate_floor()
    only reports it in missing_mandatory/missing_universal_primary when it is
    genuinely absent, so this script never even builds a gap-map entry for it.
  - skip-existing, no-clobber: floor-fill-driver.py's own per-role check
    (existing_role_keys) refuses to touch a role that is already on disk, so
    a partially-seeded dept from an interrupted prior run is never re-clobbered
    on retry (idempotent).
  - dry-run by default; --apply required to mutate.
  - never fabricates content: every role file comes from the box's real,
    shipped templates/role-library/ tree via floor-fill-driver's own
    create_role_workspace() (try_library_fill) — identical to a fresh build.
    A dept whose library source is missing is SKIPPED and reported under
    "no_library_source", never stubbed.

USAGE
  materialize-missing-departments.py [--departments-dir <dir>] [--apply] [--json]

  --departments-dir defaults to department_floor.resolve_departments_dir()
  (the same platform-appropriate resolver department-floor.py itself uses),
  so on a real box this needs no argument at all.

EXIT CODES
  0  floor already met (nothing to do), OR --apply successfully closed the gap
  1  still short after --apply (a dept's role-library source is missing —
     logged under no_library_source, never fabricated) — needs operator attention
  2  usage error / no departments dir resolvable
  3  floor is short and --apply was NOT passed (dry-run informs, does not mutate)
"""
import argparse
import importlib.util as _ilu
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(mod_name, filename):
    """Import a hyphenated sibling script as a module (mirrors
    check-floor-count-drift.py's importlib.util technique)."""
    path = SCRIPT_DIR / filename
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_DIR))
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


department_floor = _load_module("department_floor__materialize", "department-floor.py")
crw = _load_module("create_role_workspaces__materialize", "create_role_workspaces.py")

LIBRARY = SCRIPT_DIR.parent / "templates" / "role-library"
LIBRARY_INDEX = LIBRARY / "_index.json"
FLOOR_FILL_DRIVER = SCRIPT_DIR / "floor-fill-driver.py"


def _load_library_index():
    if not LIBRARY_INDEX.is_file():
        return []
    try:
        return json.loads(LIBRARY_INDEX.read_text(encoding="utf-8")).get("roles", [])
    except (OSError, ValueError):
        return []


def library_roster_for(dept_id, index_roles=None):
    """Every role the shipped library's _index.json carries for dept_id, as
    canonical role slugs. Reading _index.json (the SAME source
    create_role_workspaces.library_lookup() resolves through) rather than
    globbing the dept folder is required because the library uses TWO layouts
    interchangeably: flat '<slug>.md' files (e.g. sales/) AND per-role
    '<slug>/how-to.md' subdirectories (e.g. engineering/) — a naive glob for
    '*.md' at the dept-folder root silently returns [] for every subdirectory
    dept. Resolves dept_id -> library dept key via the SAME alias map
    create_role_workspaces.py / floor-fill-driver.py use (normalize_dept), so
    'billing-finance' finds the 'billing' library dept and 'legal' finds the
    'legal-compliance' library dept."""
    if index_roles is None:
        index_roles = _load_library_index()
    dept_key = crw.normalize_dept(dept_id)
    slugs = []
    seen = set()
    for entry in index_roles:
        if entry.get("dept", "").lower() != dept_key:
            continue
        slug = entry.get("slug", "")
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return sorted(slugs)


def build_gap_map(missing_depts):
    """missing_depts -> (gap_map, no_library_source).
    gap_map matches floor-fill-driver.py's schema exactly:
      { "<dept_id>": {"kind": "roster", "missing_roles": [...]} }
    A dept whose library source cannot be found is reported separately and
    NEVER given a fabricated/stub entry."""
    gap = {}
    no_library = []
    index_roles = _load_library_index()
    for dept_id in missing_depts:
        roster = library_roster_for(dept_id, index_roles=index_roles)
        if not roster:
            no_library.append(dept_id)
            continue
        gap[dept_id] = {"kind": "roster", "missing_roles": roster}
    return gap, no_library


def run_floor_fill_driver(gap_map, departments_dir, apply_):
    """Invoke the already-shipped v16.0.2 materializer as a subprocess
    (matches how migrate-existing-workforce.sh Step 2b calls it) so this
    script never reimplements folder/role creation."""
    with tempfile.TemporaryDirectory() as td:
        gap_file = Path(td) / "gap.json"
        gap_file.write_text(json.dumps(gap_map), encoding="utf-8")
        cmd = [sys.executable, str(FLOOR_FILL_DRIVER),
               "--gap-file", str(gap_file), "--workspace", str(departments_dir)]
        if apply_:
            cmd.append("--apply")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        report = None
        try:
            report = json.loads(proc.stdout)
        except (ValueError, TypeError):
            pass
        return proc.returncode, report, proc.stdout, proc.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--departments-dir", default=None,
                     help="departments/ dir; default = department_floor.resolve_departments_dir()")
    ap.add_argument("--build-state-file", default=None,
                     help="explicit build-state JSON file (test isolation / operator override); "
                          "default = department_floor.load_build_state() (the box's real "
                          "~/.openclaw or /data/.openclaw workforce build-state) — declines in it "
                          "are always honored, a declined dept is NEVER re-added.")
    ap.add_argument("--apply", action="store_true", help="mutate (default: dry-run report only)")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON on stdout")
    args = ap.parse_args(argv)

    dd = Path(args.departments_dir) if args.departments_dir else department_floor.resolve_departments_dir()
    if dd is None:
        _emit({"rc": 2, "reason": "no departments dir resolvable"}, args.json)
        return 2
    dd = Path(dd)
    if not dd.is_dir():
        _emit({"rc": 2, "reason": f"departments dir not found: {dd}"}, args.json)
        return 2

    build_state = None
    if args.build_state_file:
        try:
            build_state = json.loads(Path(args.build_state_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"rc": 2, "reason": f"could not read --build-state-file: {exc}"}, args.json)
            return 2

    before = department_floor.evaluate_floor(departments_dir=dd, build_state=build_state)
    missing = list(before["missing_mandatory"]) + list(before["missing_universal_primary"])

    result = {
        "departments_dir": str(dd),
        "apply": args.apply,
        "before_floor_met": before["floor_met"],
        "missing_before": missing,
    }

    if not missing:
        result.update(action="none -- floor already met", after_floor_met=True, rc=0)
        _emit(result, args.json)
        return 0

    if not args.apply:
        result.update(action="dry-run -- floor is short; re-run with --apply to materialize",
                       after_floor_met=before["floor_met"], rc=3)
        _emit(result, args.json)
        return 3

    gap_map, no_library = build_gap_map(missing)
    result["no_library_source"] = no_library

    if gap_map:
        ff_rc, ff_report, ff_stdout, ff_stderr = run_floor_fill_driver(gap_map, dd, apply_=True)
        result["floor_fill_driver_rc"] = ff_rc
        result["floor_fill_driver_report"] = ff_report if ff_report is not None else ff_stdout[-4000:]
        if ff_stderr.strip():
            result["floor_fill_driver_stderr"] = ff_stderr[-4000:]

    after = department_floor.evaluate_floor(departments_dir=dd, build_state=build_state)
    result["after_floor_met"] = after["floor_met"]
    result["missing_after"] = list(after["missing_mandatory"]) + list(after["missing_universal_primary"])
    result["action"] = "materialized via floor-fill-driver.py --apply"
    result["rc"] = 0 if after["floor_met"] else 1

    _emit(result, args.json)
    return result["rc"]


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print("============================================", file=sys.stderr)
    print("materialize-missing-departments.py", file=sys.stderr)
    print(f"departments_dir = {result.get('departments_dir')}", file=sys.stderr)
    if "before_floor_met" in result:
        print(f"before: floor_met={result['before_floor_met']} missing={result.get('missing_before')}",
              file=sys.stderr)
    if result.get("no_library_source"):
        print(f"NO LIBRARY SOURCE (skipped, never fabricated): {result['no_library_source']}",
              file=sys.stderr)
    if "after_floor_met" in result:
        print(f"after:  floor_met={result['after_floor_met']} missing={result.get('missing_after', [])}",
              file=sys.stderr)
    print(f"action: {result.get('action')}", file=sys.stderr)
    print(f"RESULT: rc={result.get('rc')}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
