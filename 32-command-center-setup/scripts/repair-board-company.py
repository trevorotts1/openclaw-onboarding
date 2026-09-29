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
     (seed-workspaces.py, same rules as the installer).

Dry run by default: prints the plan, changes nothing. --apply makes a SQLite
backup of the DB (<db>.bak-repair-board-company-<ts>) first, then commits A+B
in one transaction, then runs C. Idempotent: a second --apply finds nothing to do.

Refuses B when the board holds any OTHER real company (a shared board): moving
'default' lanes there would be a cross-tenant change.

Usage:
  repair-board-company.py [--db PATH] [--company-id UUID] [--apply]
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


def plan(cur, company_id, dept_ids):
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
    if cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engine_workspace_bootstrap'").fetchone():
        engine = {r[0] for r in cur.execute("SELECT workspace_id FROM engine_workspace_bootstrap")}
    lanes = [r[0] for r in cur.execute("SELECT id FROM workspaces WHERE company_id='default'")
             if r[0] in dept_ids or r[0] in engine]
    return {"company": {"id": company_id, "name": name, "slug": slug},
            "duplicates": dups, "other_companies": others, "default_lanes": sorted(lanes)}


def apply_ab(cur, company_id, p):
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'companies'")]
    moved = 0
    for dup_id, _, _ in p["duplicates"]:
        for t in tables:
            if "company_id" in columns(cur, t):
                moved += cur.execute(f'UPDATE "{t}" SET company_id=? WHERE company_id=?', (company_id, dup_id)).rowcount
        cur.execute("DELETE FROM companies WHERE id=?", (dup_id,))
    if p["default_lanes"]:
        marks = ",".join("?" * len(p["default_lanes"]))
        for t in tables:
            cols = columns(cur, t)
            if t == "workspaces":
                moved += cur.execute(f"UPDATE workspaces SET company_id=? WHERE company_id='default' AND id IN ({marks})",
                                     (company_id, *p["default_lanes"])).rowcount
            elif "company_id" in cols and "workspace_id" in cols:
                moved += cur.execute(f"UPDATE \"{t}\" SET company_id=? WHERE company_id='default' AND workspace_id IN ({marks})",
                                     (company_id, *p["default_lanes"])).rowcount
    return moved


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db")
    ap.add_argument("--company-id")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    seeder = _seeder()
    db = a.db or seeder.find_db()
    company_id = canonical_company_id(a.company_id)
    if not db or not Path(db).is_file():
        print("ERROR: mission-control.db not found (pass --db)", file=sys.stderr)
        return 2
    if not company_id or company_id == "default":
        print("ERROR: no canonical company id (pass --company-id or set MC_COMPANY_ID)", file=sys.stderr)
        return 2
    departments, _ = seeder.find_departments_config()
    if not departments:
        departments, _ = seeder.scan_skill23_workspaces()
    departments = seeder._normalize_departments(departments) or []
    dept_ids = {seeder._canonical_dept_slug(d.get("id", "")) for d in departments} - {""}

    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        p = plan(cur, company_id, dept_ids)
        existing = {r[0] for r in cur.execute("SELECT id FROM workspaces WHERE company_id IN (?, 'default')", (company_id,))}
        p["missing_lanes"] = sorted(dept_ids - existing)
        print(json.dumps(p, indent=2))
        if p["default_lanes"] and p["other_companies"]:
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
        backup = f"{db}.bak-repair-board-company-{ts}"
        with sqlite3.connect(backup) as dst:
            conn.backup(dst)
        print(f"Backup: {backup}")
        cur.execute("BEGIN IMMEDIATE")
        moved = apply_ab(cur, company_id, p)
        conn.commit()
        print(f"Moved {moved} row(s) to company {company_id}; removed {len(p['duplicates'])} duplicate company row(s).")
    finally:
        conn.close()
    if p["missing_lanes"]:
        comp = p["company"]
        info = seeder.find_company_info(None)
        info.update(companyId=company_id, name=comp["name"], slug=comp["slug"])
        seeder.seed(db, departments, info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
