#!/usr/bin/env python3
"""repair-userlinks.py — re-point broken USER.md symlinks under workspace departments.

Older installs left role folders with USER.md symlinks whose target no longer
exists. Every broken link is re-pointed to, in order:

  1. the real USER.md of the department the link lives in
     (<departments>/<dept>/USER.md), else
  2. the workspace USER.md (<workspace>/USER.md).

No model call, no config read, no network. Only broken symlinks named USER.md
are touched; a real (regular) USER.md file is never modified, replaced or
deleted. A link with no usable replacement is reported and left as it is.
Idempotent: a second run finds nothing broken and changes nothing.

Usage:
  repair-userlinks.py [--workspace DIR] [--departments-dir DIR]
                      [--dry-run] [--json] [--selftest]

  --workspace        OpenClaw workspace dir. Default: OPENCLAW_WORKSPACE env,
                     else the platform workspace (detect_platform), else
                     ~/.openclaw/workspace.
  --departments-dir  Default: <workspace>/departments.
  --dry-run          Report what would change; write nothing.
  --json             Machine-readable report on stdout.
  --selftest         Run the built-in hermetic check and exit.

EXIT CODES:
  0 = nothing left broken (fixed, or none found; dry-run: nothing to report as failed)
  1 = departments directory missing / unreadable
  3 = one or more broken links have no usable replacement (still broken)
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

NAME = "USER.md"
SKIP_DIRS = {".git", "node_modules"}


def default_workspace():
    env = os.environ.get("OPENCLAW_WORKSPACE", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for p in (here.parents[2] / "lib", here.parents[3] / "shared-utils"):
        sys.path.insert(0, str(p))
    try:
        from detect_platform import get_openclaw_paths
        return Path(get_openclaw_paths()["workspace"])
    except (ImportError, SystemExit, KeyError, RuntimeError):
        return Path.home() / ".openclaw" / "workspace"


def is_broken_link(p):
    # lexists-and-islink but target missing; a symlink loop also counts as broken.
    return p.is_symlink() and not os.path.exists(p)


def find_broken(departments):
    for root, dirs, files in os.walk(departments, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        # A symlink named USER.md can show up in files (file target) or dirs
        # (dir target); os.walk lists broken links in files.
        for name in files + dirs:
            if name == NAME:
                p = Path(root) / name
                if is_broken_link(p):
                    yield p


def pick_target(link, departments, workspace, planned):
    """Return (kind, real_path) or (None, None). `planned` maps links already
    re-pointed (or to be, in dry-run) to their real target, so a dry run and a
    real run choose identically."""
    rel = link.relative_to(departments)
    candidates = []
    if len(rel.parts) > 1:  # link lives inside a department
        candidates.append(("department", departments / rel.parts[0] / NAME))
    candidates.append(("workspace", workspace / NAME))
    for kind, cand in candidates:
        if cand == link:
            continue
        if cand in planned:
            return kind, planned[cand]
        if cand.is_file() and not is_broken_link(cand):  # is_file follows links
            return kind, Path(os.path.realpath(cand))
    return None, None


def repoint(link, target):
    # Relative link keeps working if the box root is moved; atomic swap so a
    # crash never leaves the role folder without a USER.md entry.
    tmp = link.with_name(".%s.repair-%d" % (NAME, os.getpid()))
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    os.symlink(os.path.relpath(target, link.parent), tmp)
    os.replace(tmp, link)


def run(workspace, departments, dry_run):
    report = {"workspace": str(workspace), "departments_dir": str(departments),
              "dry_run": dry_run, "broken_found": 0, "to_department": 0,
              "to_workspace": 0, "unresolved": 0, "errors": 0, "items": []}
    planned = {}
    # shallowest first: a department's own USER.md is settled before its roles
    for link in sorted(find_broken(departments),
                       key=lambda p: (len(p.relative_to(departments).parts), str(p))):
        report["broken_found"] += 1
        kind, target = pick_target(link, departments, workspace, planned)
        item = {"link": str(link.relative_to(departments)), "action": "unresolved",
                "target": None}
        if kind is None:
            report["unresolved"] += 1
        else:
            item.update(action="would-repoint" if dry_run else "repointed",
                        target=str(target), via=kind)
            if not dry_run:
                try:
                    repoint(link, target)
                except OSError as exc:
                    item.update(action="error", error=str(exc))
                    report["errors"] += 1
            if item["action"] != "error":
                planned[link] = target
                report["to_department" if kind == "department" else "to_workspace"] += 1
        report["items"].append(item)
    return report


def selftest():
    with tempfile.TemporaryDirectory() as t:
        ws = Path(os.path.realpath(t)) / "ws"
        deps = ws / "departments"
        for d in ("a/role1", "a/role2", "b/role1", "c/role1"):
            (deps / d).mkdir(parents=True)
        (ws / NAME).write_text("workspace user\n")
        (deps / "a" / NAME).write_text("dept a user\n")
        (deps / "c" / NAME).symlink_to(deps / "c" / "gone")  # dept USER.md itself broken
        gone = ws / "missing" / NAME
        (deps / "a/role1" / NAME).symlink_to(gone)            # -> dept a
        (deps / "b/role1" / NAME).symlink_to(gone)            # b has no USER.md -> workspace
        (deps / "c/role1" / NAME).symlink_to(gone)            # c's is broken -> workspace
        (deps / "a/role2" / NAME).write_text("real role file\n")  # must stay untouched
        before = (deps / "a/role2" / NAME).read_bytes()

        # 4 broken: a/role1, b/role1, c/USER.md, c/role1. c/USER.md (workspace)
        # is settled first, so c/role1 then points at its department.
        want = (4, 2, 2)
        r = run(ws, deps, dry_run=True)  # dry run writes nothing
        assert (r["broken_found"], r["to_department"], r["to_workspace"]) == want, r
        assert is_broken_link(deps / "a/role1" / NAME)

        r = run(ws, deps, dry_run=False)  # same plan as the dry run
        assert (r["broken_found"], r["to_department"], r["to_workspace"]) == want, r
        assert (deps / "a/role1" / NAME).read_text() == "dept a user\n"
        assert (deps / "b/role1" / NAME).read_text() == "workspace user\n"
        assert (deps / "c/role1" / NAME).read_text() == "workspace user\n"
        assert not os.path.isabs(os.readlink(deps / "a/role1" / NAME))
        assert (deps / "a/role2" / NAME).read_bytes() == before
        assert not (deps / "a/role2" / NAME).is_symlink()

        assert (deps / "c" / NAME).read_text() == "workspace user\n"
        assert run(ws, deps, dry_run=False)["broken_found"] == 0  # idempotent

        (ws / NAME).unlink()  # no workspace USER.md and no dept USER.md -> unresolved, untouched
        (deps / "b/role1" / NAME).unlink()
        (deps / "b/role1" / NAME).symlink_to(gone)
        r = run(ws, deps, dry_run=False)
        assert r["unresolved"] >= 1 and is_broken_link(deps / "b/role1" / NAME), r
    print("selftest ok")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workspace")
    ap.add_argument("--departments-dir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        selftest()
        return 0
    workspace = Path(a.workspace) if a.workspace else default_workspace()
    departments = Path(a.departments_dir) if a.departments_dir else workspace / "departments"
    if not departments.is_dir():
        print("ERROR: departments dir not found: %s" % departments, file=sys.stderr)
        return 1
    rep = run(workspace, departments, a.dry_run)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        for it in rep["items"]:
            print("%-14s %s%s" % (it["action"], it["link"],
                                  " -> " + it["target"] if it["target"] else ""))
        print("%s: %d broken, %d to department USER.md, %d to workspace USER.md, "
              "%d unresolved, %d errors" % (
                  "DRY-RUN" if a.dry_run else "REPAIR", rep["broken_found"],
                  rep["to_department"], rep["to_workspace"], rep["unresolved"],
                  rep["errors"]))
    return 3 if rep["unresolved"] or rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
