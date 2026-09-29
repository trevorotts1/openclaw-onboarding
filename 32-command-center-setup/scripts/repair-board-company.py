#!/usr/bin/env python3
"""repair-board-company.py -- put a client's Command Center board under ONE company.

Repairs the two faults that leave a client's lanes unreachable:

  A. DUPLICATE COMPANY ROWS: a row for the SAME client under another id (an
     installer step once slugified the name raw, "Acme Rocket!" -> "acme rocket!",
     and inserted a second company). Every row that references the duplicate is
     moved to the canonical company id, then the duplicate row is deleted.
  B. LANES UNDER 'default': the Command Center's own seed puts its engine queues
     (podcast, anthology) under its placeholder company 'default'. On a SINGLE-
     client board, each 'default' lane that is one of this client's departments or
     a recorded engine queue is moved to the client's company (the workspace row
     and every row that carries both its workspace_id and company_id).
  C. MISSING LANES: seeds the client's departments that have no lane yet
     (seed-workspaces.py, same rules as the installer). The department set is
     the UNION of departments.json, the build state's departments[] and the
     department folders on disk under the build's companyRoot -- the tree the
     zero-human check audits. departments.json alone missed departments added
     after it was written. Lanes are matched on the CANONICAL slug of both the
     workspace id and its slug (a CEO lane with id master-orchestrator and slug
     ceo is the ceo department), never on the raw id.

Dry run by default: prints the plan, changes nothing. --apply first writes a
ROW-LEVEL backup (<db>.repair-board-company-<ts>.rows.json: every row A+B will
change, with its old company_id, plus every companies row A deletes) -- not a
copy of the whole database, which runs to hundreds of MB -- then commits A+B in
one transaction, then runs C (additive: it only inserts missing lanes).
--restore <rows.json> puts A+B back. Idempotent: a second --apply finds nothing
to do.

Refuses B when the board holds any OTHER real company (a shared board): moving
'default' lanes there would be a cross-tenant change.

--chosen-only narrows the department set to the client's CHOSEN list
(departments.json) and moves only those 'default' lanes -- never a system or
engine queue the client did not choose (anthology, rescue-rangers), and never a
lane another company already has rows in. That scope is safe with other company
rows on the board, so B runs there too.

Usage:
  repair-board-company.py [--db PATH] [--company-id UUID] [--chosen-only] [--apply]
  repair-board-company.py [--db PATH] --restore <db>.repair-board-company-<ts>.rows.json
  (--company-id defaults to MC_COMPANY_ID, then the build state's companyId)
"""
import argparse
import importlib.util
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _seeder():
    spec = importlib.util.spec_from_file_location("seed_workspaces_repair", HERE / "seed-workspaces.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(value):
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def canonical_company_id(explicit=None):
    if explicit:
        return explicit
    if os.environ.get("MC_COMPANY_ID", "").strip():
        return os.environ["MC_COMPANY_ID"].strip()
    for p in (Path("/data/.openclaw/workspace/.workforce-build-state.json"),
              Path.home() / ".openclaw/workspace/.workforce-build-state.json"):
        try:
            cid = json.loads(p.read_text()).get("companyId")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(cid, str) and cid.strip() and cid != "default":
            return cid.strip()
    return None


def columns(cur, table):
    return [r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')]


def build_state():
    for p in (Path("/data/.openclaw/workspace/.workforce-build-state.json"),
              Path.home() / ".openclaw/workspace/.workforce-build-state.json"):
        try:
            s = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(s, dict):
            return s
    return {}


def department_set(seeder, state):
    """Every department this client has: departments.json + build state + disk."""
    departments, _ = seeder.find_departments_config()
    if not departments:
        departments, _ = seeder.scan_skill23_workspaces()
    out = list(seeder._normalize_departments(departments) or [])
    seen = {seeder._canonical_dept_slug(d.get("id", "")) for d in out}

    def add(raw, name=None):
        slug = seeder._canonical_dept_slug(str(raw or ""))
        if slug and slug not in seen:
            seen.add(slug)
            out.append({"id": slug, "name": name or slug.replace("-", " ").title(), "emoji": "\U0001F4C1"})

    for d in state.get("departments") or []:
        if isinstance(d, dict):
            add(d.get("slug") or d.get("dept_id") or d.get("id"), d.get("name"))
    root = state.get("companyRoot") or os.environ.get("ZERO_HUMAN_COMPANY_DIR")
    ddir = Path(root) / "departments" if root else None
    if ddir and ddir.is_dir():
        for p in sorted(ddir.iterdir()):
            if p.is_dir() and not p.name.startswith((".", "_")):
                add(p.name)
    return out


def covered(cur, company_id, canon):
    """Canonical slugs that already have a lane (id OR slug) under the client or 'default'."""
    have = set()
    for wid, wslug in cur.execute("SELECT id, slug FROM workspaces WHERE company_id IN (?, 'default')",
                                  (company_id,)):
        have |= {canon(wid or ""), canon(wslug or "")}
    return have - {""}


def plan(cur, company_id, dept_ids, canon=lambda x: x, chosen_only=False):
    row = cur.execute("SELECT id, name, slug FROM companies WHERE id=?", (company_id,)).fetchone()
    if not row:
        raise SystemExit(f"canonical company {company_id!r} has no companies row; refusing")
    _, name, slug = row
    dups, others = [], []
    for cid, cname, cslug in cur.execute("SELECT id, name, slug FROM companies WHERE id NOT IN (?, 'default')",
                                         (company_id,)).fetchall():
        same = norm(cslug) == norm(slug) or (norm(cname) and norm(cname) == norm(name))
        (dups if same else others).append((cid, cname, cslug))
    engine = set()
    if not chosen_only and cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engine_workspace_bootstrap'").fetchone():
        engine = {r[0] for r in cur.execute("SELECT workspace_id FROM engine_workspace_bootstrap")}
    lanes = [r[0] for r in cur.execute("SELECT id, slug FROM workspaces WHERE company_id='default'")
             if canon(r[0]) in dept_ids or canon(r[1] or "") in dept_ids or r[0] in engine]
    if chosen_only:
        # A lane some other company already works in is theirs too: leave it.
        lanes = [w for w in lanes if not _used_by_others(cur, w, company_id)]
    return {"company": {"id": company_id, "name": name, "slug": slug},
            "duplicates": dups, "other_companies": others, "default_lanes": sorted(lanes)}


def _tables(cur):
    return [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'companies'")]


def _used_by_others(cur, workspace_id, company_id):
    for t in _tables(cur):
        cols = columns(cur, t)
        if "company_id" in cols and "workspace_id" in cols and cur.execute(
                f'SELECT 1 FROM "{t}" WHERE workspace_id=? AND company_id NOT IN (?, \'default\') LIMIT 1',
                (workspace_id, company_id)).fetchone():
            return True
    return False


def changes(cur, p):
    """(table, WHERE clause, params) for every row set A+B moves to the client."""
    out = []
    tables = _tables(cur)
    for dup_id, _, _ in p["duplicates"]:
        out += [(t, "company_id=?", (dup_id,)) for t in tables if "company_id" in columns(cur, t)]
    if p["default_lanes"]:
        marks = ",".join("?" * len(p["default_lanes"]))
        for t in tables:
            cols = columns(cur, t)
            if t == "workspaces":
                out.append((t, f"company_id='default' AND id IN ({marks})", tuple(p["default_lanes"])))
            elif "company_id" in cols and "workspace_id" in cols:
                out.append((t, f"company_id='default' AND workspace_id IN ({marks})", tuple(p["default_lanes"])))
    return out


def row_backup(cur, p):
    """Every row A+B changes, as it is NOW: {updates: [[table, rowid, company_id]],
    deleted_companies: [row dicts]}. Raises on a table without a rowid."""
    updates = []
    for t, where, params in changes(cur, p):
        updates += [[t, rid, cid] for rid, cid in
                    cur.execute(f'SELECT rowid, company_id FROM "{t}" WHERE {where}', params)]
    cols = columns(cur, "companies")
    deleted = [dict(zip(cols, cur.execute("SELECT * FROM companies WHERE id=?", (d[0],)).fetchone()))
               for d in p["duplicates"]]
    return {"updates": updates, "deleted_companies": deleted}


def apply_ab(cur, company_id, p):
    moved = sum(cur.execute(f'UPDATE "{t}" SET company_id=? WHERE {where}', (company_id, *params)).rowcount
                for t, where, params in changes(cur, p))
    for dup_id, _, _ in p["duplicates"]:
        cur.execute("DELETE FROM companies WHERE id=?", (dup_id,))
    return moved


def restore(db, backup_path):
    b = json.loads(Path(backup_path).read_text())
    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        for row in b["deleted_companies"]:
            cur.execute(f'INSERT OR IGNORE INTO companies ({",".join(row)}) VALUES ({",".join("?" * len(row))})',
                        tuple(row.values()))
        for t, rid, cid in b["updates"]:
            cur.execute(f'UPDATE "{t}" SET company_id=? WHERE rowid=?', (cid, rid))
        conn.commit()
    finally:
        conn.close()
    print(f"Restored {len(b['updates'])} row(s) and {len(b['deleted_companies'])} company row(s) from {backup_path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db")
    ap.add_argument("--company-id")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--chosen-only", action="store_true",
                    help="move/seed only the client's chosen departments (departments.json)")
    ap.add_argument("--restore", metavar="ROWS_JSON", help="undo an --apply from its row backup")
    a = ap.parse_args(argv)
    seeder = _seeder()
    db = a.db or seeder.find_db()
    if a.restore:
        if not db or not Path(db).is_file():
            print("ERROR: mission-control.db not found (pass --db)", file=sys.stderr)
            return 2
        return restore(db, a.restore)
    company_id = canonical_company_id(a.company_id)
    if not db or not Path(db).is_file():
        print("ERROR: mission-control.db not found (pass --db)", file=sys.stderr)
        return 2
    if not company_id or company_id == "default":
        print("ERROR: no canonical company id (pass --company-id or set MC_COMPANY_ID)", file=sys.stderr)
        return 2
    canon = seeder._canonical_dept_slug
    if a.chosen_only:
        departments = list(seeder._normalize_departments(seeder.find_departments_config()[0]) or [])
        if not departments:
            print("ERROR: --chosen-only needs the client's departments.json; none found", file=sys.stderr)
            return 2
    else:
        departments = department_set(seeder, build_state())
    dept_ids = {canon(d.get("id", "")) for d in departments} - {""}

    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        p = plan(cur, company_id, dept_ids, canon, a.chosen_only)
        p["missing_lanes"] = sorted(dept_ids - covered(cur, company_id, canon))
        p["canonical_slug_module"] = "shared-utils/canonical_slug.py" if seeder._HAS_CANONICAL_SLUG else "INLINE FALLBACK"
        print(json.dumps(p, indent=2))
        if p["default_lanes"] and p["other_companies"] and not a.chosen_only:
            print("REFUSING step B: this board holds other companies "
                  f"{[c[0] for c in p['other_companies']]}; moving 'default' lanes would cross tenants.",
                  file=sys.stderr)
            p["default_lanes"] = []
        if not a.apply:
            print("DRY RUN: nothing changed. Re-run with --apply.")
            return 0
        if not (p["duplicates"] or p["default_lanes"] or p["missing_lanes"]):
            print("Nothing to repair.")
            return 0
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = f"{db}.repair-board-company-{ts}.rows.json"
        cur.execute("BEGIN IMMEDIATE")
        Path(backup).write_text(json.dumps(row_backup(cur, p), indent=1))
        print(f"Row backup: {backup}  (undo: --restore {backup})")
        moved = apply_ab(cur, company_id, p)
        conn.commit()
        print(f"Moved {moved} row(s) to company {company_id}; removed {len(p['duplicates'])} duplicate company row(s).")
    finally:
        conn.close()
    if p["missing_lanes"]:
        comp = p["company"]
        info = seeder.find_company_info(None)
        info.update(companyId=company_id, name=comp["name"], slug=comp["slug"])
        missing = set(p["missing_lanes"])
        seeder.seed(db, [d for d in departments if canon(d.get("id", "")) in missing], info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
