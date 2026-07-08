#!/usr/bin/env python3
"""
seed-dashboard-content.py — v10.14.24

Populates the Mission Control dashboard's `companies`, `agents`, and `tasks`
tables so the Kanban board renders real cards on first load.

Background:
  Skill 32's `seed-workspaces.py` populates the `workspaces` table. The
  dashboard repo's `npm run db:seed` populates demo BlackCEO content. But
  neither one writes the `companies` row that drives the header brand name +
  colors, nor the `agents` and `tasks` rows that make the Kanban non-empty.
  Result: every client's dashboard rendered five empty columns. This script
  closes that gap.

Reads from (in priority order):
  1. /data/projects/command-center/config/company-config.json   (Skill 32 writes this)
  2. /data/.openclaw/workspace/zero-human-company/<slug>/company-config.json
  3. .workforce-build-state.json  (companyName/industry/brandColor)
  4. Env: $COMPANY_NAME, $COMPANY_BRAND_COLORS

Idempotent: uses INSERT OR REPLACE for the companies row; only inserts agents
and tasks if the workspace has none yet (so re-running won't pile up duplicates).

Schema-tolerant: reads PRAGMA table_info for each table and only INSERTs
columns that actually exist. This survives schema drift between dashboard
repo versions.
"""
import sqlite3, json, os, sys, secrets, subprocess
from datetime import datetime, timezone
from pathlib import Path

# PRD 1.3: import the single shared DB resolver.
_SHARED_UTILS = Path(__file__).resolve().parent.parent.parent / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
try:
    from resolve_db import find_dashboard_db as _shared_find_dashboard_db, is_db_found  # type: ignore
    _HAS_SHARED_RESOLVER = True
except ImportError:
    _HAS_SHARED_RESOLVER = False


def scaffold_agent_files(agent_slug, agent_name, department):
    """Invoke scaffold-agent-files.sh for a dept-head agent.

    Writes IDENTITY/SOUL/MEMORY/HEARTBEAT (if missing) and (re)creates
    USER/AGENTS/TOOLS symlinks. Safe to call repeatedly — script is
    idempotent.

    Trevor's agent-file architecture (v10.14.29):
      - SHARED across all agents: USER.md, AGENTS.md, TOOLS.md
      - PER-AGENT: IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md
      - Sub-agents are excluded (handled by Skill 23 post-build).
    """
    scaffolder = Path(__file__).resolve().parent / "scaffold-agent-files.sh"
    if not scaffolder.is_file():
        print(f"  [scaffold] WARN: {scaffolder} not found — skipping per-agent file scaffold", file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            ["bash", str(scaffolder),
             "--agent-slug", agent_slug,
             "--agent-name", agent_name,
             "--department", department],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"  [scaffold] WARN: scaffolder exited rc={result.returncode} for {agent_slug}: "
                  f"{result.stderr.strip()[:300]}", file=sys.stderr)
            return False
        return True
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"  [scaffold] WARN: scaffolder failed for {agent_slug}: {e}", file=sys.stderr)
        return False


def find_db():
    """
    PRD 1.3: delegate to the shared resolver when available so every script
    uses the same ordered candidate list, including the VPS canonical path
    /data/projects/command-center/ that was missing from this script.
    """
    if _HAS_SHARED_RESOLVER:
        p = _shared_find_dashboard_db()
        return str(p) if is_db_found(p) else None
    # DATA-08: honor the app's DB env vars first, even on this bootstrap path.
    for _ev in ("DASHBOARD_DB_PATH", "DATABASE_PATH"):
        _v = os.environ.get(_ev)
        if _v and Path(_v).is_file():
            return str(_v)
    # Fallback for bootstrap installs.
    candidates = [
        Path.home() / "projects/command-center/mission-control.db",
        Path.home() / "projects/mission-control/mission-control.db",
        Path("/data/projects/command-center/mission-control.db"),
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def find_company_config():
    """Returns dict with name/slug/industry/owner_name/brand colors."""
    info = {
        "name": "",
        "slug": "",
        "industry": "",
        "owner_name": "",
        "primary": "#1f2937",
        "accent":  "#3b82f6",
    }

    # 1. Skill 32's config/company-config.json (the canonical place dashboard reads from)
    cfg_path = Path("/data/projects/command-center/config/company-config.json")
    if not cfg_path.exists():
        cfg_path = Path.home() / "projects/command-center/config/company-config.json"
    if cfg_path.exists():
        try:
            cfg = json.load(open(cfg_path))
            info["name"]       = cfg.get("companyName") or cfg.get("name") or info["name"]
            info["slug"]       = cfg.get("slug") or info["slug"]
            info["industry"]   = cfg.get("industry") or info["industry"]
            info["owner_name"] = cfg.get("ownerName") or cfg.get("owner_name") or info["owner_name"]
            brand = cfg.get("brandColors") or cfg.get("brand") or {}
            info["primary"] = brand.get("primary", info["primary"])
            info["accent"]  = brand.get("accent",  info["accent"])
        except (json.JSONDecodeError, OSError):
            pass

    # 2. ZHC workspace company-config.json
    if not info["name"]:
        for root in [
            Path("/data/.openclaw/workspace/zero-human-company"),
            Path.home() / "clawd/zero-human-company",
        ]:
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir()):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                p = entry / "company-config.json"
                if not p.exists():
                    continue
                try:
                    cfg = json.load(open(p))
                    info["name"]       = cfg.get("name") or cfg.get("companyName") or info["name"]
                    info["slug"]       = cfg.get("slug") or entry.name
                    info["industry"]   = cfg.get("industry") or info["industry"]
                    info["owner_name"] = cfg.get("ownerName") or cfg.get("owner_name") or info["owner_name"]
                    brand = cfg.get("brand") or cfg.get("brandColors") or {}
                    info["primary"] = brand.get("primary", info["primary"])
                    info["accent"]  = brand.get("accent",  info["accent"])
                    if info["name"]:
                        break
                except (json.JSONDecodeError, OSError):
                    continue
            if info["name"]:
                break

    # 3. .workforce-build-state.json (Skill 23 writes companyName/industry/brandColor here)
    if not info["name"]:
        for p in [
            Path("/data/.openclaw/workspace/.workforce-build-state.json"),
            Path.home() / ".openclaw/workspace/.workforce-build-state.json",
        ]:
            if p.exists():
                try:
                    s = json.load(open(p))
                    info["name"]     = info["name"]     or s.get("companyName", "")
                    info["industry"] = info["industry"] or s.get("industry", "")
                    info["primary"]  = s.get("brandColor") or info["primary"]
                    break
                except (json.JSONDecodeError, OSError):
                    pass

    # 4. Env vars
    info["name"] = os.environ.get("COMPANY_NAME", info["name"]).strip()
    brand_env = os.environ.get("COMPANY_BRAND_COLORS", "").strip()
    if brand_env:
        try:
            colors = json.loads(brand_env)
            info["primary"] = colors.get("primary", info["primary"])
            info["accent"]  = colors.get("accent",  info["accent"])
        except json.JSONDecodeError:
            pass

    if not info["slug"] and info["name"]:
        info["slug"] = info["name"].lower().replace(" ", "-").replace(",", "")[:40]
    if not info["name"]:
        info["name"] = "Client"
        info["slug"] = info["slug"] or "client"

    return info


def insert_company(db, info):
    co_cols = [r[1] for r in db.execute("PRAGMA table_info(companies)")]
    if not co_cols:
        print("WARN: companies table missing — skipping company insert", file=sys.stderr)
        return None

    # Prefer the slug as the primary key if the schema uses slug-as-id
    existing = db.execute("SELECT id FROM companies WHERE slug = ? LIMIT 1", (info["slug"],)).fetchone()
    company_id = existing[0] if existing else secrets.token_hex(8)

    data = {
        "id": company_id,
        "name": info["name"],
        "slug": info["slug"],
        "owner_name": info["owner_name"],
        "industry": info["industry"],
        "primary_color": info["primary"],
        "secondary_color": info["accent"],
        "accent_color": info["accent"],
        "brand_primary": info["primary"],
        "brand_accent":  info["accent"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    insert_cols = [c for c in data if c in co_cols]
    placeholders = ",".join("?" * len(insert_cols))
    sql = f"INSERT OR REPLACE INTO companies ({','.join(insert_cols)}) VALUES ({placeholders})"
    db.execute(sql, [data[c] for c in insert_cols])
    print(f"  companies: upsert id={company_id} name={info['name']!r} primary={info['primary']}")
    return company_id


def insert_agents_and_tasks(db, info):
    ws_cols = [r[1] for r in db.execute("PRAGMA table_info(workspaces)")]
    if not ws_cols:
        print("WARN: workspaces table missing — run seed-workspaces.py first", file=sys.stderr)
        return 0, 0

    ag_cols = [r[1] for r in db.execute("PRAGMA table_info(agents)")]
    tk_cols = [r[1] for r in db.execute("PRAGMA table_info(tasks)")]
    if not ag_cols or not tk_cols:
        print("WARN: agents or tasks table missing — dashboard schema mismatch", file=sys.stderr)
        return 0, 0

    db.row_factory = sqlite3.Row
    workspaces = list(db.execute("SELECT * FROM workspaces"))
    if not workspaces:
        print("WARN: workspaces table is empty — run seed-workspaces.py first", file=sys.stderr)
        return 0, 0

    agents_added = 0
    tasks_added = 0
    now = datetime.now(timezone.utc).isoformat()

    for ws in workspaces:
        ws_dict = dict(ws)
        ws_id = ws_dict.get("id")
        ws_slug = ws_dict.get("slug") or ws_dict.get("name", "").lower().replace(" ", "-")
        ws_name = ws_dict.get("name", ws_slug)

        # Skip if this workspace already has agents (idempotency guard)
        existing_agents = db.execute(
            "SELECT COUNT(*) FROM agents WHERE workspace_id = ?", (ws_id,)
        ).fetchone()[0]

        if existing_agents == 0:
            ag_id = secrets.token_hex(8)
            ag_data = {
                "id": ag_id,
                "workspace_id": ws_id,
                "name": f"{ws_name} Lead",
                "role": f"{ws_name} Department Head",
                "persona": f"dept-{ws_slug}",
                "description": f"Heads the {ws_name} department in your AI workforce.",
                "specialist_type": "permanent",
                "status": "standby",
                "created_at": now,
                "updated_at": now,
            }
            insert_cols = [c for c in ag_data if c in ag_cols]
            sql = f"INSERT INTO agents ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
            try:
                db.execute(sql, [ag_data[c] for c in insert_cols])
                agents_added += 1
                # Trevor's agent-file architecture (v10.14.29): every new
                # dept-head agent gets its per-agent IDENTITY/SOUL/MEMORY/
                # HEARTBEAT files + symlinks to shared USER/AGENTS/TOOLS.
                # Best-effort — never fails the dashboard seed.
                scaffold_agent_files(ws_slug, ag_data["name"], ws_slug)
            except sqlite3.Error as e:
                print(f"  agent insert for {ws_slug} failed: {e}", file=sys.stderr)
                ag_id = None
        else:
            row = db.execute(
                "SELECT id FROM agents WHERE workspace_id = ? LIMIT 1", (ws_id,)
            ).fetchone()
            ag_id = row[0] if row else None

        # Skip if this workspace already has tasks
        existing_tasks = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE workspace_id = ?", (ws_id,)
        ).fetchone()[0]

        if existing_tasks == 0 and ag_id:
            tk_id = secrets.token_hex(8)
            tk_data = {
                "id": tk_id,
                "workspace_id": ws_id,
                "department": ws_slug,
                "title": f"Welcome to {ws_name}",
                "description": (
                    f"This is your {ws_name} department's first task. "
                    f"Click to edit. Your AI workforce will populate real "
                    f"tasks as work comes in."
                ),
                "status": "backlog",
                "priority": "medium",
                "assigned_agent_id": ag_id,
                "created_by_agent_id": ag_id,
                "created_at": now,
                "updated_at": now,
            }
            insert_cols = [c for c in tk_data if c in tk_cols]
            sql = f"INSERT INTO tasks ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
            try:
                db.execute(sql, [tk_data[c] for c in insert_cols])
                tasks_added += 1
            except sqlite3.Error as e:
                print(f"  task insert for {ws_slug} failed: {e}", file=sys.stderr)

    return agents_added, tasks_added


def update_logo_config():
    """Empty logoUrl → useLogoUrl hook falls through to text-SVG fallback
    which renders the company name from the companies row. Drop a per-client
    PNG at public/logo-<slug>.png and set logoUrl accordingly to override."""
    for p in [
        Path("/data/projects/command-center/public/logo-config.json"),
        Path.home() / "projects/command-center/public/logo-config.json",
    ]:
        if p.parent.is_dir():
            try:
                json.dump({"logoUrl": ""}, open(p, "w"), indent=2)
                print(f"  logo-config: text-SVG fallback set at {p}")
                return
            except OSError as e:
                print(f"  logo-config update failed at {p}: {e}", file=sys.stderr)


def main():
    db_path = find_db()
    if not db_path:
        print("ERROR: mission-control.db not found", file=sys.stderr)
        sys.exit(1)

    info = find_company_config()
    print(f"DB: {db_path}")
    print(f"Company: {info['name']!r} (slug={info['slug']})")
    print(f"Brand: primary={info['primary']} accent={info['accent']}")
    print()
    print("Seeding dashboard content...")

    db = sqlite3.connect(db_path)
    try:
        company_id = insert_company(db, info)
        agents_added, tasks_added = insert_agents_and_tasks(db, info)
        db.commit()
        print(f"  agents added: {agents_added}")
        print(f"  tasks added:  {tasks_added}")
    finally:
        db.close()

    update_logo_config()

    # Verification
    db = sqlite3.connect(db_path)
    try:
        c = db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        w = db.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
        a = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        t = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        print(f"\nFinal counts: companies={c} workspaces={w} agents={a} tasks={t}")
        if c >= 1 and w >= 1 and a >= 1 and t >= 1:
            print("OK — Kanban will render cards on next dashboard load.")
        else:
            print("WARN — one or more tables still empty; check logs above", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()
