#!/usr/bin/env python3
"""
seed-workspaces.py — v9.6.1
Seeds department workspaces into the Mission Control database.

Reads departments dynamically from (in priority order):
  1. ~/clawd/zero-human-company/<slug>/departments.json    (v9.6.0 canonical ZHC)
  2. ~/clawd/zhc/<slug>/departments.json                   (short-alias)
  3. ~/Downloads/openclaw-master-files/company-discovery/  (pre-v9.6.0 legacy)
  4. ~/clawd/departments/departments.json                  (very old legacy)
  5. Falls back to scanning workspace folders for dept directories

ALSO reads company name + brand colors + industry from:
  - ~/clawd/zero-human-company/<slug>/company-config.json  (v9.6.1+)
  - workforce-interview-answers.md (from interview)
  - $COMPANY_NAME env var
  - $COMPANY_BRAND_COLORS env var (JSON: '{"primary":"#000","accent":"#f00"}')

The number of departments seeded MUST match what the client actually said in
the interview. Do NOT hardcode 17 — read from departments.json.

Run this after the Command Center is installed and the DB is created.
"""
import sqlite3, json, os, sys, re
from pathlib import Path

# PRD 1.3: import the single shared DB resolver.
# PRD 1.5: import the canonical dept slug normaliser.
_SHARED_UTILS = Path(__file__).resolve().parent.parent.parent / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
try:
    from resolve_db import find_dashboard_db as _shared_find_dashboard_db  # type: ignore
    _HAS_SHARED_RESOLVER = True
except ImportError:
    _HAS_SHARED_RESOLVER = False

try:
    from canonical_slug import canonical_dept_slug as _canonical_dept_slug  # type: ignore
    _HAS_CANONICAL_SLUG = True
except ImportError:
    _HAS_CANONICAL_SLUG = False
    # Inline fallback so the script still works without the shared-utils import
    # (e.g. very early bootstrap before shared-utils is installed on the box).
    import re as _re
    def _canonical_dept_slug(raw: str) -> str:  # type: ignore
        if not raw or not isinstance(raw, str):
            return ""
        s = raw.strip().lower()
        if s.startswith("dept-"):
            s = s[5:]
        if s.endswith("-dept"):
            s = s[:-5]
        s = s.replace(" ", "-").replace("_", "-")
        s = _re.sub(r"-{2,}", "-", s)
        return s.strip("-")


def find_db():
    """
    PRD 1.3: delegate to the shared resolver when available so every script
    uses the same ordered candidate list, including the VPS canonical path
    /data/projects/command-center/ that was missing from this script.
    """
    if _HAS_SHARED_RESOLVER:
        p = _shared_find_dashboard_db()
        return str(p) if p.exists() else None
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

def _zhc_root_candidates():
    """All possible Zero Human Company root locations, in priority order.

    PRD 1.9: the canonical root (master_files/zero-human-company) comes FIRST.
    Legacy roots follow for backward-compat reading of existing companies.
    Nothing WRITES to legacy roots — that is enforced in build-workforce.py.

    NOTE: Path("~/...") does NOT expand the tilde — use Path.home() or
    Path(os.path.expanduser("~/...")) instead. (PRD item 1.7)
    """
    # Try to get the canonical root from the shared path resolver first.
    try:
        from detect_platform import get_openclaw_paths as _gop
        _p = _gop()
        canonical = _p["company_root"]  # master_files/zero-human-company
    except Exception:
        canonical = None

    roots = []
    if canonical is not None:
        roots.append(canonical)
    roots.extend([
        Path.home() / "clawd" / "zero-human-company",   # v9.6.0+ legacy
        Path.home() / "clawd" / "zhc",                   # short-alias legacy
        Path(os.path.expanduser("~/clawd/zero-human-company")),
        Path(os.path.expanduser("~/clawd/zhc")),
    ])
    return roots


def _scan_zhc_for_company_slugs():
    """Return list of (slug, zhc_root_path) tuples for every company found."""
    results = []
    for root in _zhc_root_candidates():
        if root.is_dir():
            for entry in sorted(root.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    results.append((entry.name, root))
    return results


def _normalize_departments(data):
    """Coerce a loaded departments.json payload into a list of dicts.

    departments.json in the wild comes in three shapes, all of which must seed:
      1. canonical  : [{"id": "marketing", "name": "Marketing", "emoji": "📢"}, ...]
      2. bare-string : ["marketing", "sales", ...]            (legacy / hand-written)
      3. dict-of-dicts: {"marketing": {"name": "Marketing"}, ...}  (some CC exports)

    Previously seed() assumed shape (1) and called dept.get('id') on every entry,
    so a string entry from shape (2)/(3) raised
    `'str' object has no attribute 'get'` at the seed loop — the exact crash that
    made `sync-extensions.sh --converge` Step 4 fail. This normaliser makes the
    seeder accept all three shapes. The bare slug is canonicalised and a human
    'name' is derived (title-cased, hyphens→spaces) when not supplied.
    """
    if data is None:
        return None

    # Shape 3: dict keyed by slug. Fold the key in as id, merge the value dict.
    if isinstance(data, dict):
        items = []
        for k, v in data.items():
            if isinstance(v, dict):
                entry = dict(v)
                entry.setdefault("id", k)
                items.append(entry)
            else:
                items.append({"id": k})
        data = items

    if not isinstance(data, list):
        return None

    normalized = []
    for dept in data:
        if isinstance(dept, str):
            slug = dept.strip()
            if not slug:
                continue
            display = slug.replace("dept-", "").replace("-dept", "")
            display = display.replace("-", " ").replace("_", " ").strip().title()
            normalized.append({"id": slug, "name": display or slug})
        elif isinstance(dept, dict):
            entry = dict(dept)
            # Tolerate dicts that carry a slug under a different key.
            if "id" not in entry:
                entry["id"] = entry.get("slug") or entry.get("dept") or entry.get("key") or ""
            if not entry.get("name"):
                base = str(entry.get("id", "")).replace("dept-", "").replace("-dept", "")
                base = base.replace("-", " ").replace("_", " ").strip().title()
                entry["name"] = base or str(entry.get("id", ""))
            normalized.append(entry)
        # Anything else (None, int, list) is silently dropped — it cannot be a dept.
    return normalized


def find_departments_config():
    """Look for departments.json generated by Skill 23.

    v9.6.1 priority order:
      1. ZHC canonical: ~/clawd/zero-human-company/<slug>/departments.json
      2. ZHC short-alias: ~/clawd/zhc/<slug>/departments.json
      3. Legacy company-discovery: ~/Downloads/openclaw-master-files/company-discovery/departments.json
      4. Older legacy: ~/clawd/departments/departments.json
      5. Pre-existing CC config dirs (last resort)

    If $COMPANY_SLUG is set, prefer that company's folder. Otherwise pick the
    most-recently-modified ZHC folder (matches "the one the client just built").
    """
    explicit_root = os.environ.get('ZERO_HUMAN_COMPANY_DIR')
    if explicit_root:
        source = Path(explicit_root)/'departments.json'
        return _normalize_departments(json.loads(source.read_text())), str(source)
    target_slug = os.environ.get("COMPANY_SLUG", "").strip()

    # Build prioritized candidate list
    candidates = []

    # 1+2. ZHC paths — try the target slug first, then most-recent
    zhc_companies = _scan_zhc_for_company_slugs()
    if target_slug:
        for slug, root in zhc_companies:
            if slug == target_slug:
                candidates.append(root / slug / "departments.json")
    # Most-recently-modified ZHC company folder
    zhc_with_mtime = []
    for slug, root in zhc_companies:
        dj = root / slug / "departments.json"
        if dj.exists():
            zhc_with_mtime.append((dj.stat().st_mtime, dj))
    zhc_with_mtime.sort(reverse=True)
    for _, dj in zhc_with_mtime:
        if dj not in candidates:
            candidates.append(dj)

    # 3+4+5. Legacy paths
    candidates.extend([
        Path.home() / "Downloads/openclaw-master-files/company-discovery/departments.json",
        Path(os.path.expanduser("~/Downloads/openclaw-master-files/company-discovery/departments.json")),
        Path.home() / "clawd/departments/departments.json",
        Path.home() / "projects/command-center/config/departments.json",
        Path.home() / "projects/mission-control/config/departments.json",
        Path("/opt/mission-control/config/departments.json"),
        Path("/app/config/departments.json"),
    ])

    for p in candidates:
        if p.exists():
            try:
                with open(p) as f:
                    data = json.load(f)
                if data:  # Not empty
                    # Coerce string / dict-of-dicts payloads into list-of-dicts so the
                    # seed loop's dept.get('id') never hits a bare str (the --converge
                    # Step-4 crash). Done at the single load boundary so every caller
                    # downstream sees a uniform shape.
                    data = _normalize_departments(data)
                    if data:
                        print(f"  [departments.json] Found {len(data)} departments at: {p}", file=sys.stderr)
                        return data, str(p)
            except (json.JSONDecodeError, OSError) as e:
                print(f"  [departments.json] Skipping {p}: {e}", file=sys.stderr)
                continue
    return None, None

def scan_skill23_workspaces():
    """Fall back: scan Skill 23 workspace folders to build department list.

    v9.6.1: checks ZHC paths FIRST so a v9.6.0+ install discovers correctly.
    """
    workspace_dirs = []
    # v9.6.0+ ZHC canonical and short-alias paths (one per company found)
    for slug, root in _scan_zhc_for_company_slugs():
        workspace_dirs.append(root / slug / "departments")
    # Legacy paths
    workspace_dirs.extend([
        Path.home() / "clawd/departments",
        Path(os.path.expanduser("~/clawd/departments")),
        Path.home() / ".openclaw/workspaces/command-center",
        Path.home() / "Downloads/openclaw-master-files/my AI company departments",
    ])
    # Also scan ~/Downloads/ for any department folders
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        for item in sorted(downloads.iterdir()):
            if item.is_dir() and ('dept' in item.name.lower() or 'department' in item.name.lower()):
                workspace_dirs.append(item)
    
    # Default emoji map
    emoji_map = {
        'marketing': '📢', 'sales': '💰', 'billing': '💳', 'finance': '💳',
        'support': '🛟', 'operations': '⚙️', 'hr': '👥', 'creative': '🎨',
        'graphics': '🖼️', 'video': '🎬', 'audio': '🎵', 'legal': '⚖️',
        'technology': '💻', 'it': '💻', 'product': '🚀', 'research': '🔬',
        'training': '📚', 'ceo': '👔', 'com': '👔', 'analytics': '📊',
    }
    
    departments = []
    parent_folder_name = None
    
    for ws_dir in workspace_dirs:
        if not ws_dir.exists():
            continue
        # Store parent folder name as potential company name
        parent_folder_name = ws_dir.parent.name if ws_dir.name == "command-center" else ws_dir.name
        for folder in sorted(ws_dir.iterdir()):
            if folder.is_dir() and not folder.name.startswith('.'):
                # PRD 1.5: use the shared canonical_dept_slug normaliser so the folder-
                # scanning path and the departments.json path produce identical ids.
                # Handles "dept-" prefix, "-dept" suffix, spaces, underscores, mixed case.
                dept_id = _canonical_dept_slug(folder.name)
                if not dept_id:
                    continue
                dept_name = dept_id.replace('-', ' ').replace('_', ' ').title()
                # Try to read name from SOUL.md if it exists
                soul = folder / "SOUL.md"
                if soul.exists():
                    with open(soul) as f:
                        for line in f:
                            if line.startswith('# '):
                                dept_name = line.strip('# \n')
                                break
                emoji = '📁'
                for key, icon in emoji_map.items():
                    if key in dept_id:
                        emoji = icon
                        break
                departments.append({
                    'id': dept_id,
                    'name': dept_name,
                    'emoji': emoji
                })
        if departments:
            break  # Use first directory that has departments
    
    return departments, parent_folder_name

def find_company_info(parent_folder_name=None):
    """
    Find company name + brand colors + industry. Returns dict:
      { "name": str, "slug": str, "industry": str,
        "brand_primary": str (hex), "brand_accent": str (hex),
        "brand_text": str (hex) }

    v9.6.1 priority order:
      1. $COMPANY_NAME / $COMPANY_BRAND_COLORS env vars
      2. ~/clawd/zero-human-company/<slug>/company-config.json
      3. workforce-interview-answers.md (ZHC path first, then legacy)
      4. parent folder name (last resort)
    """
    info = {
        "name": "",
        "slug": "",
        "industry": "",
        "brand_primary": "#1f2937",   # neutral default (slate-800)
        "brand_accent":  "#3b82f6",   # neutral default (blue-500)
        "brand_text":    "#f8fafc",   # neutral default (slate-50)
    }

    # Explicit company context wins over ambient filesystem discovery.
    explicit_root = os.environ.get('ZERO_HUMAN_COMPANY_DIR')
    if explicit_root:
        cfg = json.loads((Path(explicit_root)/'company-config.json').read_text())
        info.update(name=cfg.get('name') or cfg.get('companyName') or '',
                    slug=cfg.get('slug') or cfg.get('companySlug') or '',
                    companyId=cfg.get('companyId') or cfg.get('company_id'))
        if not info['name'] or not info['slug']: raise ValueError('explicit company config missing identity')
        if os.environ.get('MC_COMPANY_ID') and info.get('companyId') and os.environ['MC_COMPANY_ID'] != info['companyId']:
            raise ValueError('explicit company identity conflict')
        return info

    # 1. Env vars
    info["name"] = os.environ.get("COMPANY_NAME", "").strip()
    brand_env = os.environ.get("COMPANY_BRAND_COLORS", "").strip()
    if brand_env:
        try:
            colors = json.loads(brand_env)
            info["brand_primary"] = colors.get("primary", info["brand_primary"])
            info["brand_accent"]  = colors.get("accent",  info["brand_accent"])
            info["brand_text"]    = colors.get("text",    info["brand_text"])
        except json.JSONDecodeError:
            pass

    # 2. ZHC company-config.json (v9.6.1+)
    if not info["name"]:
        for slug, root in _scan_zhc_for_company_slugs():
            cfg_path = root / slug / "company-config.json"
            if cfg_path.exists():
                try:
                    with open(cfg_path) as fh:
                        cfg = json.load(fh)
                    info["name"]     = cfg.get("name", "") or info["name"]
                    info["slug"]     = cfg.get("slug", slug)
                    info["industry"] = cfg.get("industry", "") or info["industry"]
                    brand = cfg.get("brand", {})
                    info["brand_primary"] = brand.get("primary", info["brand_primary"])
                    info["brand_accent"]  = brand.get("accent",  info["brand_accent"])
                    info["brand_text"]    = brand.get("text",    info["brand_text"])
                    if info["name"]:
                        break
                except (json.JSONDecodeError, OSError):
                    continue

    # 3. workforce-interview-answers.md — ZHC paths FIRST, then legacy
    answer_files = []
    for slug, root in _scan_zhc_for_company_slugs():
        answer_files.append(root / slug / "workforce-interview-answers.md")
    answer_files.extend([
        Path.home() / "Downloads/openclaw-master-files/company-discovery/workforce-interview-answers.md",
        Path(os.path.expanduser("~/Downloads/openclaw-master-files/company-discovery/workforce-interview-answers.md")),
        Path.home() / ".openclaw/workspace/company-discovery/workforce-interview-answers.md",
    ])

    if not info["name"]:
        for f in answer_files:
            if f.exists():
                try:
                    with open(f) as fh:
                        content = fh.read()
                    patterns = [
                        r'(?:company|business)\s*name\s*[:\-]\s*(.+?)(?:\n|$)',
                        r'#+\s*(?:company|business)\s*name\s*\n+(.+?)(?:\n|$)',
                        r'\*\*Q:\*\*\s+What is the name of your business\?\s*\n+\*\*A:\*\*\s+(.+?)(?:\n|$)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            info["name"] = match.group(1).strip()
                            if info["name"]:
                                break
                    # Industry capture
                    if not info["industry"]:
                        m = re.search(r'\*\*Q:\*\*\s+What industry.+?\*\*A:\*\*\s+(.+?)(?:\n|$)',
                                       content, re.IGNORECASE | re.DOTALL)
                        if m:
                            info["industry"] = m.group(1).strip()
                    if info["name"]:
                        break
                except Exception:
                    pass

    # 4. Parent folder name (last resort)
    if not info["name"] and parent_folder_name and parent_folder_name not in ['workspaces', 'command-center', 'departments']:
        clean = parent_folder_name.replace('-dept', '').replace('_dept', '')
        clean = clean.replace('-', ' ').replace('_', ' ').title()
        info["name"] = clean

    if not info["name"]:
        info["name"] = "My Company"

    if not info["slug"]:
        info["slug"] = re.sub(r'[^a-z0-9]+', '-', info["name"].lower()).strip('-') or "my-company"

    return info

def _adopt_unused_engine_bootstrap(cur, dept_id, company_id):
    """Claim only a recorded migration placeholder, never a live/shared queue.

    Called inside seed's transaction. Row IDs and agent/skill references stay
    unchanged. The original rows are backed up in the CC migration-owned ledger.
    """
    if not cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='engine_workspace_bootstrap'").fetchone():
        return False
    record = cur.execute("SELECT original_workspace_json, adopted_company_id FROM engine_workspace_bootstrap WHERE workspace_id=?", (dept_id,)).fetchone()
    if not record or record[1]:
        return False
    names = [r[1] for r in cur.execute('PRAGMA table_info(workspaces)')]
    raw = cur.execute('SELECT * FROM workspaces WHERE id=?', (dept_id,)).fetchone()
    if not raw:
        return False
    row = dict(zip(names, raw))
    original = json.loads(record[0])
    # Auto-created head_agent_id is allowed; identity, display and lifecycle
    # changes indicate a customized queue and must not be adopted.
    for key in ('id', 'slug', 'name', 'description', 'icon', 'sort_order', 'company_id', 'archived_at', 'archived_reason', 'user_md'):
        if row.get(key) != original.get(key):
            return False
    if row.get('company_id') != 'default' or company_id in ('default', '', None) or row.get('user_md') or row.get('archived_reason'):
        return False
    agent_cols = [r[1] for r in cur.execute('PRAGMA table_info(agents)')]
    agents = [dict(zip(agent_cols, r)) for r in cur.execute('SELECT * FROM agents WHERE workspace_id=?', (dept_id,))] if agent_cols else []
    roles = {f'qc-agent-{dept_id}': 'qc', f'research-agent-{dept_id}': 'research',
             f'da-agent-{dept_id}': 'devils-advocate', f'head-agent-{dept_id}': 'leadership'}
    if dept_id == 'podcast':
        roles.update({'podcast-editor': 'specialist', 'podcast-producer': 'specialist', 'show-notes-writer': 'specialist'})
    labels = {'qc': ('QC Specialist', 'QC Specialist'),
              'research': ('Research Specialist', 'Research Specialist'),
              'devils-advocate': ("Devil's Advocate", "Devil's Advocate"),
              'leadership': ('Department Head', 'Department Head')}
    specialist_names = {'podcast-editor': 'Podcast Editor', 'podcast-producer': 'Podcast Producer', 'show-notes-writer': 'Show Notes Writer'}
    for agent in agents:
        role_type = roles.get(agent['id'])
        if role_type in labels:
            suffix, expected_role = labels[role_type]
            expected_name = f"{row['name']} {suffix}"
        else:
            expected_name = expected_role = specialist_names.get(agent['id'])
        if agent.get('name') != expected_name or agent.get('role') != expected_role:
            return False
        if (roles.get(agent['id']) != agent.get('role_type') or agent.get('status') != 'standby'
                or agent.get('openclaw_agent_id') or agent.get('openclaw_session_id') or agent.get('is_master')
                or any(agent.get(k) for k in ('soul_md', 'user_md', 'agents_md', 'tools_md', 'memory_md', 'persona'))):
            return False
    agent_ids = [a['id'] for a in agents]
    if row.get('head_agent_id') and row['head_agent_id'] not in agent_ids:
        return False
    # Inspect all real tables, including legacy non-FK references. Any work or
    # runtime history means this is an existing system queue, not a placeholder.
    # Known seeded agents and their static skill bindings alone are harmless.
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        if table in ('workspaces', 'agents', 'engine_workspace_bootstrap', 'agent_skills'):
            continue
        quoted = '"' + table.replace('"', '""') + '"'
        cols = [r[1] for r in cur.execute(f'PRAGMA table_info({quoted})')]
        refs = {r[3]: r[2] for r in cur.execute(f'PRAGMA foreign_key_list({quoted})')}
        for col in cols:
            qcol = '"' + col.replace('"', '""') + '"'
            if (col == 'workspace_id' or col.endswith('_workspace_id') or refs.get(col) == 'workspaces') and cur.execute(f'SELECT 1 FROM {quoted} WHERE {qcol}=? LIMIT 1', (dept_id,)).fetchone():
                return False
            if (col == 'agent_id' or col.endswith('_agent_id') or refs.get(col) == 'agents') and agent_ids:
                params = ','.join('?' for _ in agent_ids)
                if cur.execute(f'SELECT 1 FROM {quoted} WHERE {qcol} IN ({params}) LIMIT 1', agent_ids).fetchone():
                    return False
    bindings = []
    if 'agent_skills' in tables and agent_ids:
        params = ','.join('?' for _ in agent_ids)
        binding_cols = [r[1] for r in cur.execute('PRAGMA table_info(agent_skills)')]
        bindings = [dict(zip(binding_cols, r)) for r in cur.execute(f'SELECT * FROM agent_skills WHERE agent_id IN ({params})', agent_ids)]
        if any(b['skill_id'] != 'skill-58' or b['agent_id'] not in ('podcast-editor', 'podcast-producer', 'show-notes-writer') for b in bindings):
            return False
    backup = json.dumps({'workspace': row, 'agents': agents, 'agent_skills': bindings}, sort_keys=True)
    cur.execute("UPDATE engine_workspace_bootstrap SET adopted_company_id=?, adoption_backup_json=?, adopted_at=datetime('now') WHERE workspace_id=? AND adopted_company_id IS NULL", (company_id, backup, dept_id))
    cur.execute("UPDATE workspaces SET company_id=? WHERE id=? AND company_id='default'", (company_id, dept_id))
    print(f'  PREPARED BOOTSTRAP: {dept_id} (commits only when the entire seed succeeds; agent IDs preserved)')
    return True

def seed(db_path, departments, company_info):
    """
    v9.6.1: company_info is now a dict (name + slug + industry + brand colors)
    instead of a bare name string. Brand colors persist in companies.config
    so the dashboard can render them.
    """
    conn = sqlite3.connect(db_path)
    try:
        _seed_transaction(conn, departments, company_info)
    finally:
        # Closing rolls back every pending write if any ownership/schema guard
        # raised, including failures before the department loop.
        conn.close()


def _seed_transaction(conn, departments, company_info):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("BEGIN IMMEDIATE")

    # Ensure tables exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            industry TEXT,
            config TEXT DEFAULT '{}'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            icon TEXT,
            company_id TEXT DEFAULT 'default'
        )
    """)

    # Create company entry — write brand colors + industry into config blob
    company_slug = company_info["slug"]
    company_name = company_info["name"]
    requested_id = company_info.get('companyId') or os.environ.get('MC_COMPANY_ID')
    existing_company = cur.execute('SELECT id FROM companies WHERE slug=?',(company_slug,)).fetchone()
    if requested_id and existing_company and existing_company[0] != requested_id:
        raise ValueError('company slug belongs to a different canonical company ID')
    company_id = requested_id or (existing_company[0] if existing_company else company_slug)
    collision = cur.execute('SELECT slug FROM companies WHERE id=?',(company_id,)).fetchone()
    if collision and collision[0] != company_slug: raise ValueError('canonical company ID belongs to a different slug')
    company_config = json.dumps({
        "brand": {
            "primary": company_info["brand_primary"],
            "accent":  company_info["brand_accent"],
            "text":    company_info["brand_text"],
        },
    })

    # Upsert — refresh name/industry/config in case they changed between runs
    cur.execute("""
        INSERT INTO companies (id, name, slug, industry, config)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          industry=excluded.industry,
          config=excluded.config
    """, (company_id, company_name, company_slug, company_info["industry"], company_config))
    print(f"  Company: {company_name} (slug={company_slug}, industry={company_info['industry'] or 'n/a'})")
    print(f"  Brand: primary={company_info['brand_primary']} accent={company_info['brand_accent']}")

    existing = {row[0] for row in cur.execute("SELECT id FROM workspaces WHERE company_id=?", (company_id,)).fetchall()}
    inserted = 0
    skipped = 0

    # v9.6.1: STRICT match to client's chosen departments.
    # The number seeded MUST equal len(departments). Do NOT fall back to 17
    # defaults if the client said they wanted 15 or 50.
    print(f"  Departments to seed: {len(departments)} (this is what the client chose in the interview)")

    # Defense-in-depth: if a caller hands us un-normalized data (bare strings or a
    # dict-of-dicts), coerce here too so the loop below can rely on dict entries.
    departments = _normalize_departments(departments) or []

    for dept in departments:
        # PRD 1.5: normalise the id through canonical_dept_slug so we get the bare
        # slug in ALL cases: "dept-marketing" -> "marketing", "Marketing" -> "marketing",
        # "marketing-dept" -> "marketing".  Replaces the old raw_id[5:] hack which only
        # handled the leading "dept-" case and would silently pass through mixed-case,
        # underscore, or trailing-"-dept" forms unchanged.
        raw_id = dept.get('id', '')
        dept_id = _canonical_dept_slug(raw_id)
        if not dept_id:
            continue
        owner = cur.execute('SELECT company_id FROM workspaces WHERE id=? OR slug=?',(dept_id,dept_id)).fetchall()
        if any(row[0] != company_id for row in owner):
            # UUID must be supplied by the canonical launch context. A company
            # name or slug guessed by discovery is not adoption authorization.
            if not requested_id or not _adopt_unused_engine_bootstrap(cur, dept_id, company_id):
                conn.rollback()
                conn.close()
                raise ValueError(f'department {dept_id} belongs to a different company or an active/custom system queue; refusing shared-client mutation. Resume the supported installer; do not rewrite company IDs.')
            existing.add(dept_id)
        if dept_id in existing:
            skipped += 1
            continue
        # Idempotency: INSERT OR IGNORE prevents a UNIQUE(slug) crash when the
        # dept list contains duplicate canonical slugs, or when workspaces were
        # partially seeded in a prior run. The pre-loop `existing` set handles
        # the already-in-db case; OR IGNORE is the last-resort safety net for
        # rows inserted earlier in this same loop iteration.
        cur.execute("""
            INSERT OR IGNORE INTO workspaces (id, name, slug, description, icon, company_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            dept_id,
            dept['name'],
            dept_id,
            f"{dept['name']} department workspace",
            dept.get('emoji', '📁'),
            company_id
        ))
        if cur.rowcount:
            print(f"  INSERTED: {dept_id} ({dept['name']}) {dept.get('emoji', '📁')}")
            inserted += 1
            # Update in-loop guard so duplicate canonical slugs in the same
            # dept list are counted as skipped rather than double-inserted.
            existing.add(dept_id)
        else:
            print(f"  SKIPPED (conflict): {dept_id} ({dept['name']})")
            skipped += 1

    conn.commit()
    conn.close()
    print(f"\nSeeding complete. Inserted: {inserted} | Skipped (already existed): {skipped} | Client expected: {len(departments)}")

if __name__ == "__main__":
    db = find_db()
    if not db:
        print("ERROR: Could not find mission-control.db. Is the Command Center installed?")
        sys.exit(1)

    # Try departments.json first, fall back to scanning folders
    departments, source = find_departments_config()
    parent_folder_name = None
    
    if departments:
        print(f"Source: {source}")
    else:
        print("departments.json empty or missing. Scanning Skill 23 workspace folders...")
        departments, parent_folder_name = scan_skill23_workspaces()
        source = "Skill 23 workspace scan"

    if not departments:
        print("ERROR: No departments found. Run Skill 23 (AI Workforce Blueprint) first.")
        sys.exit(1)

    company_info = find_company_info(parent_folder_name)

    print(f"DB: {db}")
    print(f"Source: {source}")
    print(f"Company: {company_info['name']} (slug: {company_info['slug']})")
    print(f"Industry: {company_info['industry'] or 'n/a'}")
    print(f"Brand: primary={company_info['brand_primary']} accent={company_info['brand_accent']}")
    print(f"Departments found: {len(departments)} (will seed exactly this many — no 17-default fallback)")
    print("Seeding workspaces...")
    seed(db, departments, company_info)

    # v9.6.5: auto-generate brand.css so the Kanban frontend renders client colors.
    # The generator finds the public/ dir automatically; logs warning if it can't.
    import subprocess
    brand_css_script = Path(__file__).parent / "generate-brand-css.py"
    if brand_css_script.is_file():
        try:
            subprocess.run(
                ["python3", str(brand_css_script), "--company-slug", company_info["slug"]],
                check=False, timeout=10,
            )
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"  [BRAND-CSS] Auto-generation failed: {e}", file=sys.stderr)
            print(f"  [BRAND-CSS] Run manually: python3 {brand_css_script}", file=sys.stderr)
    else:
        print(f"  [BRAND-CSS] Script not found at {brand_css_script}; skipped", file=sys.stderr)
