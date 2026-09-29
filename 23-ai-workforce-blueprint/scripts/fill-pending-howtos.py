#!/usr/bin/env python3
"""fill-pending-howtos.py -- the scripted runner for PENDING-SOPS.md.

Every role whose how-to.md is a PENDING stub (no role-library template matched
its exact title at build time) carries a one-shot instruction: copy the NEAREST
role-library template family and token-fill it. Nothing ran that instruction, so
the stubs sat forever. This does, deterministically (no model call):

  1. exact library match (the library may have gained the role since the build)
  2. nearest template by role title in the SAME library department
  3. nearest template by role title across the whole library (a department the
     library does not cover, e.g. a vertical pack's departments)

A match must clear the title-similarity cutoff (--cutoff 0.6 within the
department; the much stricter --library-cutoff 0.85 across departments, because a
loose cross-department match -- "Buyer Agent" -> a QC agent -- would plant the
wrong SOPs) and the same 3072-byte substance floor create_role_workspaces.try_library_fill enforces; otherwise
the role stays PENDING and is reported as needing authoring (populate-sops-from-
manifest.py queues it). Only a how-to.md that is STILL a PENDING stub is ever
written -- filled content is never touched. Idempotent.

Usage:
  fill-pending-howtos.py [--departments-dir DIR] [--dept SLUG ...] [--cutoff 0.6]
                         [--library-cutoff 0.85] [--apply]
Dry run by default. Exit 0 = nothing left pending; 3 = roles still pending.
"""
import argparse
import difflib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import create_role_workspaces as crw  # noqa: E402

PENDING_MARKERS = ("PENDING - FILL FROM LIBRARY", "how-to.md (stub)")
MIN_BYTES = 3072  # same floor as create_role_workspaces.try_library_fill
SKIP_DIRS = {"memory", "devils-advocate"}


def is_pending(how_to):
    try:
        head = how_to.read_text(encoding="utf-8", errors="replace")[:600]
    except OSError:
        return False
    return any(m in head for m in PENDING_MARKERS)


def role_title(role_dir):
    how_to = role_dir / "how-to.md"
    try:
        first = how_to.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        first = ""
    m = re.match(r"#\s*(.+?)\s+[-—]+\s+how-to\.md", first)
    if m:
        return m.group(1).strip()
    return re.sub(r"^\d+[-_]", "", role_dir.name).replace("-", " ").title()


def pending_roles(departments_dir, depts=None):
    out = []
    for dept_dir in sorted(p for p in Path(departments_dir).iterdir() if p.is_dir()):
        if depts and dept_dir.name not in depts:
            continue
        for role_dir in sorted(p for p in dept_dir.iterdir() if p.is_dir() and p.name not in SKIP_DIRS):
            if (role_dir / "how-to.md").is_file() and is_pending(role_dir / "how-to.md"):
                out.append((dept_dir, role_dir))
    return out


def nearest_template(title, dept_slug, cutoff, library_cutoff=0.85):
    """(doc_path, role_entry, how) for the nearest template, or (None, None, reason)."""
    doc, entry = crw.library_lookup(title, dept_slug)
    if doc:
        return doc, entry, "exact"
    skill_dir = crw._resolve_skill_dir()
    by_dept = crw._build_library_index(skill_dir)
    key = crw._clean_role_key(title, "and")

    def best(pool, floor):
        # pool: {normalized_key: role_entry}
        hit = difflib.get_close_matches(key, list(pool), n=1, cutoff=floor)
        return pool[hit[0]] if hit else None

    same = by_dept.get(crw.normalize_dept(dept_slug), {})
    entry, how = (best(same, cutoff), "nearest-in-dept") if same else (None, None)
    if entry is None:
        everything = {}
        for d in sorted(by_dept):
            for k, e in by_dept[d].items():
                everything.setdefault(k, e)
        entry, how = best(everything, library_cutoff), "nearest-in-library"
    if entry is None:
        return None, None, f"no comparable template (dept >= {cutoff}, library >= {library_cutoff})"
    doc = skill_dir / entry.get("path", "")
    if not doc.is_file():
        doc = skill_dir / "templates" / "role-library" / entry["dept"] / f"{entry['slug']}.md"
    return (doc, entry, how) if doc.is_file() else (None, None, "template file missing")


def fill_one(dept_dir, role_dir, cutoff, apply, library_cutoff=0.85):
    title = role_title(role_dir)
    doc, entry, how = nearest_template(title, dept_dir.name, cutoff, library_cutoff)
    if not doc:
        return False, how
    dept_name = dept_dir.name.replace("-", " ").title()
    filled = crw.fill_tokens(doc.read_text(encoding="utf-8"), title, dept_name, False, role_entry=entry)
    if len(filled.encode("utf-8")) < MIN_BYTES:
        return False, f"template {entry['dept']}/{entry['slug']} fills below {MIN_BYTES}B"
    header = (f"<!-- workforce-provenance: source=role-library role-slug={entry.get('slug', '?')} "
              f"dept={entry.get('dept', '?')} content_sha={entry.get('content_sha', 'sha256:UNKNOWN')} "
              f"content_version={entry.get('content_version', '?')} "
              f"instantiated={datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
              f"generator=fill-pending-howtos.py match={how} filled-for={role_dir.name} -->\n")
    if apply:
        how_to = role_dir / "how-to.md"
        if not is_pending(how_to):  # filled meanwhile: never overwrite real content
            return False, "no longer pending"
        tmp = how_to.with_name(f".how-to.md.tmp-{os.getpid()}")
        tmp.write_text(header + filled, encoding="utf-8")
        os.replace(tmp, how_to)
    return True, f"{how}: {entry['dept']}/{entry['slug']}"


def default_departments_dir():
    try:
        from detect_platform import get_openclaw_paths  # noqa: E402
        company = get_openclaw_paths().get("company_dir")
    except (Exception, SystemExit):
        company = None
    return Path(company) / "departments" if company else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--departments-dir")
    ap.add_argument("--dept", action="append", help="only these department folders (repeatable)")
    ap.add_argument("--cutoff", type=float, default=0.6)
    ap.add_argument("--library-cutoff", type=float, default=0.85)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    ddir = Path(a.departments_dir) if a.departments_dir else default_departments_dir()
    if not ddir or not ddir.is_dir():
        print("ERROR: departments dir not found (pass --departments-dir)", file=sys.stderr)
        return 2
    left = 0
    roles = pending_roles(ddir, set(a.dept or []))
    for dept_dir, role_dir in roles:
        ok, why = fill_one(dept_dir, role_dir, a.cutoff, a.apply, a.library_cutoff)
        if not ok:
            left += 1
        verb = ("FILLED" if a.apply else "WOULD FILL") if ok else "STILL PENDING"
        print(f"[fill-pending-howtos] {verb} {dept_dir.name}/{role_dir.name} ({why})")
    print(f"[fill-pending-howtos] {len(roles)} pending role(s); {len(roles) - left} "
          f"{'filled' if a.apply else 'fillable'}; {left} need authoring"
          + ("" if a.apply else " -- DRY RUN, nothing written (use --apply)"))
    return 3 if left else 0


if __name__ == "__main__":
    sys.exit(main())
