#!/usr/bin/env python3
"""Skill 32 — SOP V2 Library ingester (idempotent).

Applies migration 028 (V2 schema additions) if needed, then inserts /
upserts every SOP from the supplied jsonl file. Resolves upstream
dependencies by slug. Seeds client_template_vars with platform defaults.

Usage: ingest-sop-library.py <client-slug> <sops.jsonl> [db-path]

Safe to re-run: every write is INSERT OR REPLACE / INSERT OR IGNORE,
keyed off stable IDs derived from each SOP's slug. Used by Skill 32's
fresh install AND by client update flows that ship a refreshed library.
"""
import sqlite3, json, os, re, secrets, sys, hashlib
from datetime import datetime, timezone
from pathlib import Path

# PRD 1.3: resolve the DB via the single shared resolver when no explicit path is
# passed, so a direct run (no db-path arg) finds the DB on Mac AND VPS instead of
# assuming the VPS-only /data path.
_SHARED_UTILS = Path(__file__).resolve().parent.parent.parent / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
try:
    from resolve_db import find_dashboard_db as _shared_find_dashboard_db, is_db_found  # type: ignore
    _HAS_SHARED_RESOLVER = True
except ImportError:
    _HAS_SHARED_RESOLVER = False


def _default_db() -> str:
    """Resolve mission-control.db when the caller passes no explicit path.
    Prefers the shared resolver (Mac ~/projects/command-center first, then VPS
    /data/projects/command-center); falls back to add-department.sh's list."""
    if _HAS_SHARED_RESOLVER:
        p = _shared_find_dashboard_db()
        if is_db_found(p):
            return str(p)
    # DATA-08: honor the app's DB env vars first, even on this bootstrap path.
    for _ev in ("DASHBOARD_DB_PATH", "DATABASE_PATH"):
        _v = os.environ.get(_ev)
        if _v and Path(_v).is_file():
            return str(_v)
    for cand in (
        Path.home() / "projects/command-center/mission-control.db",
        Path.home() / "projects/mission-control/mission-control.db",
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
        Path("/data/projects/command-center/mission-control.db"),
    ):
        if cand.is_file():
            return str(cand)
    return "/data/projects/command-center/mission-control.db"


def _resolve_crm_platform(client_slug: str) -> str:
    """Prefer the interview answer over a blind GoHighLevel default.

    Mirrors 23-ai-workforce-blueprint/scripts/create_role_workspaces.py: the CRM
    is derived from the company-config.json connectedSystems list (GoHighLevel is
    the fleet default; HubSpot/Salesforce override when present). An explicit
    $CRM_PLATFORM env var wins. Downstream INSERT OR IGNORE still means a value a
    prior interview step already wrote is never clobbered.
    """
    env_override = os.environ.get("CRM_PLATFORM", "").strip()
    if env_override:
        return env_override
    for cfg_path in (
        Path("/data/projects/command-center/config/company-config.json"),
        Path.home() / "projects/command-center/config/company-config.json",
        Path("/data/.openclaw/workspace/zero-human-company") / client_slug / "company-config.json",
    ):
        try:
            if not cfg_path.is_file():
                continue
            cfg = json.load(open(cfg_path))
        except (OSError, json.JSONDecodeError):
            continue
        blob = str(cfg.get("connectedSystems") or cfg.get("connected_systems") or "").lower()
        if "hubspot" in blob:
            return "HubSpot"
        if "salesforce" in blob:
            return "Salesforce"
        return "GoHighLevel"
    return "GoHighLevel"


def _ghl_pit_present() -> bool:
    """Presence-only check (never reads/prints the value) for the GHL PIT in the
    canonical secrets file. Used to warn the operator before stamping GoHighLevel."""
    for env_path in (
        Path.home() / ".openclaw/secrets/.env",
        Path("/data/.openclaw/secrets/.env"),
    ):
        try:
            if not env_path.is_file():
                continue
            for line in env_path.read_text().splitlines():
                s = line.strip()
                if s.startswith("GOHIGHLEVEL_API_KEY=") and s.split("=", 1)[1].strip():
                    return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------------------
# UNIVERSAL-SOPS CRAFT-CLUSTER INGEST
#
# The gap this closes: an engine's operating SOPs live in
# universal-sops/<cluster>/ as markdown, NOT in the shared sops.jsonl release
# asset and NOT in 23-ai-workforce-blueprint/templates/role-library/<dept>/sops/.
# Nothing ever read them into the Command Center SOP library, so a department
# whose entire runbook lives in a craft cluster showed ZERO SOPs in the
# dashboard and in semantic SOP search, on every box, forever. The podcast
# engine is exactly that case: seven SOP-PODCAST-0*.md files, department
# 'podcast', none of them in the library.
#
# This ingest reads the markdown, derives a library row per file, and upserts it
# through the same stable identity the JSONL pass uses (sop_ + sha256(slug)), so
# it is idempotent by slug and re-runnable on every roll. It NEVER downloads,
# never embeds (zero cost on the client's key), and never deletes.
#
# The map is explicit on purpose: a cluster is ingested only when a department
# genuinely owns it. Adding a cluster is one line here.
# ---------------------------------------------------------------------------
CRAFT_CLUSTER_DEPARTMENTS = {
    "podcast-craft": "podcast",
}


def _resolve_universal_sops(explicit=None):
    """universal-sops/ lives beside the numbered skill dirs, in the repo and in
    an installed skills tree alike, so relative resolution works in both."""
    if explicit:
        p = Path(explicit)
        return p if p.is_dir() else None
    here = Path(__file__).resolve()
    for base in (here.parent.parent.parent, here.parent.parent.parent.parent):
        cand = base / "universal-sops"
        if cand.is_dir():
            return cand
    return None


def _craft_sop_row(md_path, department, cluster):
    """Derive ONE library row from a craft-cluster SOP markdown file.

    Shape matches the JSONL rows the shared library ships (see the upsert
    below): steps is a list of {name, order} dicts because that is what
    shared-utils/sop-embed-once/embed_sop_library.py reads.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()

    title = ""
    description = ""
    steps = []
    for line in lines:
        s = line.strip()
        if not title and s.startswith("# "):
            title = s[2:].strip()
            continue
        if s.startswith("## "):
            steps.append({"name": s[3:].strip(), "order": len(steps) + 1})
            continue
        # The first PROSE line, not the bold metadata header block these SOPs
        # open with (**Cluster:**, **Skill:**, **Owning role:**, ...).
        if (title and not description and s
                and not s.startswith(("#", "|", "---", ">", "- ", "* ", "1.", "!["))
                and not re.match(r"^\*\*[^*]{1,80}:?\*\*", s)):
            description = s.replace("**", "").strip()

    slug = md_path.stem
    if not title:
        title = slug
    return {
        "slug": slug,
        "name": title[:300],
        "description": description[:1000],
        "version": 1,
        "department": department,
        "cadence": None,
        "source_role": None,
        "confidence": None,
        "confidence_tier": None,
        "estimated_minutes": None,
        "time_of_day": None,
        "source_file_url": "universal-sops/%s/%s" % (cluster, md_path.name),
        "task_keywords": " ".join(slug.lower().replace("-", " ").split()),
        "steps": steps,
        "success_criteria": "",
        "prerequisites": None,
        "persona_hints": [],
        "template_vars_used": [],
        "layer_version": "v2",
        "dependencies_upstream": [],
    }


def _upsert_craft_rows(conn, rows):
    """Same stable identity and same INSERT OR REPLACE contract as the JSONL
    pass, so a craft SOP and a library SOP can never collide or diverge."""
    cols_present = [c[1] for c in conn.execute("PRAGMA table_info(sops)")]
    stamp = datetime.now(timezone.utc).isoformat()
    written = 0
    for row in rows:
        sop_id = "sop_" + hashlib.sha256(row["slug"].encode()).hexdigest()
        existing = conn.execute("SELECT slug FROM sops WHERE id = ?", (sop_id,)).fetchone()
        if existing and existing[0] != row["slug"]:
            print(f"  FATAL: hash collision - sop_id={sop_id} maps to both "
                  f"slug={existing[0]!r} and slug={row['slug']!r}. Aborting.", file=sys.stderr)
            return -1
        data = dict(row)
        data.pop("dependencies_upstream", None)
        data["id"] = sop_id
        data["steps"] = json.dumps(row["steps"], default=str)
        data["persona_hints"] = json.dumps(row["persona_hints"])
        data["template_vars_used"] = json.dumps(row["template_vars_used"])
        data["created_at"] = stamp
        data["updated_at"] = stamp
        cols = [c for c in data if c in cols_present]
        sql = "INSERT OR REPLACE INTO sops (%s) VALUES (%s)" % (
            ",".join(cols), ",".join("?" * len(cols)))
        conn.execute(sql, [data[c] for c in cols])
        written += 1
    conn.commit()
    return written


def ingest_craft_clusters(conn, universal_sops_dir, clusters=None):
    """Ingest every mapped craft cluster. Returns (written, clusters_seen)."""
    total = 0
    seen = []
    wanted = clusters or CRAFT_CLUSTER_DEPARTMENTS
    for cluster, department in sorted(wanted.items()):
        cdir = Path(universal_sops_dir) / cluster
        if not cdir.is_dir():
            print(f"  craft cluster {cluster}: directory not present at {cdir}; skipped")
            continue
        rows = []
        for md in sorted(cdir.glob("SOP-*.md")):
            row = _craft_sop_row(md, department, cluster)
            if row:
                rows.append(row)
        if not rows:
            print(f"  craft cluster {cluster}: no SOP-*.md files found in {cdir}; skipped")
            continue
        n = _upsert_craft_rows(conn, rows)
        if n < 0:
            return (-1, seen)
        print(f"  craft cluster {cluster} -> department {department}: upserted {n} SOP(s)")
        total += n
        seen.append(cluster)
    return (total, seen)


def _craft_main(argv):
    """Standalone mode: ingest-sop-library.py --craft-clusters [--db P] [--universal-sops D]"""
    db_path = None
    usops = None
    i = 0
    while i < len(argv):
        if argv[i] == "--db" and i + 1 < len(argv):
            db_path = argv[i + 1]; i += 2; continue
        if argv[i] == "--universal-sops" and i + 1 < len(argv):
            usops = argv[i + 1]; i += 2; continue
        i += 1
    db_path = db_path or _default_db()
    if not Path(db_path).is_file():
        print(f"[craft-sops] mission-control.db not found at {db_path}; nothing ingested", file=sys.stderr)
        return 0
    root = _resolve_universal_sops(usops)
    if root is None:
        print("[craft-sops] universal-sops/ not found next to the skill directories; nothing ingested", file=sys.stderr)
        return 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    have_sops = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sops'").fetchone()[0]
    if not have_sops:
        print("[craft-sops] the sops table does not exist yet (Skill 32 dashboard not installed); nothing ingested",
              file=sys.stderr)
        conn.close()
        return 0
    print(f"[craft-sops] db={db_path} universal-sops={root}")
    written, seen = ingest_craft_clusters(conn, root)
    conn.close()
    if written < 0:
        return 1
    print(f"[craft-sops] done: {written} row(s) across {len(seen)} cluster(s)")
    return 0


if "--craft-clusters" in sys.argv:
    sys.exit(_craft_main(sys.argv[1:]))


CLIENT = sys.argv[1]
JSONL = sys.argv[2]
DB = sys.argv[3] if len(sys.argv) > 3 else _default_db()

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# ---- Migration 028: V2 SOP schema additions ----
print(f"[{CLIENT}] migration 028: V2 schema")
sop_cols = [c[1] for c in db.execute("PRAGMA table_info(sops)")]
add_cols = [
    ("cadence", "TEXT"),
    ("source_role", "TEXT"),
    ("confidence", "REAL"),
    ("confidence_tier", "TEXT"),
    ("estimated_minutes", "INTEGER"),
    ("time_of_day", "TEXT"),
    ("source_file_url", "TEXT"),
    ("prerequisites", "TEXT"),
    ("template_vars_used", "TEXT"),
    ("layer_version", "TEXT DEFAULT 'v2'"),
]
added = 0
for col, typ in add_cols:
    if col not in sop_cols:
        db.execute(f"ALTER TABLE sops ADD COLUMN {col} {typ}")
        added += 1
db.execute("CREATE INDEX IF NOT EXISTS idx_sops_cadence ON sops(cadence)")
db.execute("CREATE INDEX IF NOT EXISTS idx_sops_layer ON sops(layer_version)")
db.execute("CREATE INDEX IF NOT EXISTS idx_sops_confidence_tier ON sops(confidence_tier)")
db.execute("CREATE INDEX IF NOT EXISTS idx_sops_source_role ON sops(source_role)")

db.executescript("""
    CREATE TABLE IF NOT EXISTS sop_dependencies (
      id TEXT PRIMARY KEY,
      parent_sop_id TEXT NOT NULL REFERENCES sops(id),
      prereq_sop_id TEXT NOT NULL REFERENCES sops(id),
      dependency_type TEXT,
      notes TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      UNIQUE(parent_sop_id, prereq_sop_id)
    );
    CREATE INDEX IF NOT EXISTS idx_sop_deps_parent ON sop_dependencies(parent_sop_id);
    CREATE INDEX IF NOT EXISTS idx_sop_deps_prereq ON sop_dependencies(prereq_sop_id);

    CREATE TABLE IF NOT EXISTS client_template_vars (
      id TEXT PRIMARY KEY,
      client_slug TEXT NOT NULL,
      var_name TEXT NOT NULL,
      var_value TEXT,
      default_value TEXT,
      description TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now')),
      UNIQUE(client_slug, var_name)
    );
    CREATE INDEX IF NOT EXISTS idx_ctv_client ON client_template_vars(client_slug);
""")

mig_cols = [c[1] for c in db.execute("PRAGMA table_info(_migrations)")]
db.execute("DELETE FROM _migrations WHERE id='028'")
if "name" in mig_cols:
    db.execute("INSERT INTO _migrations (id, name) VALUES ('028', 'sop_v2_autonomous_execution')")
else:
    db.execute("INSERT INTO _migrations (id) VALUES ('028')")
db.commit()
print(f"  added {added} columns; dependency + template-var tables ready")

# ---- Pass 1: upsert all SOPs ----
print(f"[{CLIENT}] pass 1: upsert SOPs")
slug_to_id = {}
deps_pending = []
sop_cols = [c[1] for c in db.execute("PRAGMA table_info(sops)")]
inserted = 0
errors = 0
now = datetime.now(timezone.utc).isoformat()

with open(JSONL) as f:
    for line in f:
        sop = json.loads(line)
        slug = sop.get("slug", "")
        if not slug:
            continue
        # U078: collision-resistant deterministic identifier. The old 60-char
        # truncation caused 26 collision groups covering 88 slugs, collapsing to
        # 26 surviving identifiers — 62 records lost. Full sha256 hash is
        # collision-resistant and deterministic.
        sop_id = "sop_" + hashlib.sha256(slug.encode()).hexdigest()

        # U078: explicit collision detection — abort rather than silently replace.
        # If this sop_id already exists with a DIFFERENT slug, that's a hash
        # collision (astronomically unlikely with sha256, but we check anyway).
        existing = db.execute("SELECT slug FROM sops WHERE id = ?", (sop_id,)).fetchone()
        if existing and existing[0] != slug:
            print(f"  FATAL: hash collision detected — sop_id={sop_id} maps to both "
                  f"slug={existing[0]!r} and slug={slug!r}. Aborting.", file=sys.stderr)
            sys.exit(1)

        slug_to_id[slug] = sop_id
        deps_pending.append((sop_id, slug, sop.get("dependencies_upstream", [])))
        data = {
            "id": sop_id,
            "slug": slug,
            "name": sop.get("name", ""),
            "description": sop.get("description") or "",
            "version": sop.get("version", 1),
            "department": sop.get("department"),
            "cadence": sop.get("cadence"),
            "source_role": sop.get("source_role"),
            "confidence": sop.get("confidence"),
            "confidence_tier": sop.get("confidence_tier"),
            "estimated_minutes": sop.get("estimated_minutes"),
            "time_of_day": sop.get("time_of_day"),
            "source_file_url": sop.get("source_file_url"),
            "task_keywords": sop.get("task_keywords", ""),
            "steps": json.dumps(sop.get("steps", []), default=str),
            "success_criteria": sop.get("success_criteria") or "",
            "prerequisites": sop.get("prerequisites"),
            "persona_hints": json.dumps(sop.get("persona_hints", [])),
            "template_vars_used": json.dumps(sop.get("template_vars_used", [])),
            "layer_version": sop.get("layer_version", "v2"),
            "created_at": now,
            "updated_at": now,
        }
        cols = [c for c in data if c in sop_cols]
        sql = f"INSERT OR REPLACE INTO sops ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})"
        try:
            db.execute(sql, [data[c] for c in cols])
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  upsert fail slug={slug}: {e}")
db.commit()
print(f"  upserted: {inserted}, errors: {errors}")

# ---- Pass 2: resolve dependencies by slug ----
print(f"[{CLIENT}] pass 2: resolve upstream dependencies")
dep_inserted = 0
dep_unresolved = 0
for parent_id, parent_slug, upstreams in deps_pending:
    for prereq_slug in upstreams:
        prereq_id = slug_to_id.get(prereq_slug)
        if not prereq_id:
            dep_unresolved += 1
            continue
        try:
            db.execute(
                "INSERT OR IGNORE INTO sop_dependencies (id, parent_sop_id, prereq_sop_id, dependency_type) VALUES (?,?,?,?)",
                (secrets.token_hex(8), parent_id, prereq_id, "upstream"),
            )
            dep_inserted += 1
        except Exception:
            pass
db.commit()
print(f"  inserted: {dep_inserted}, unresolved (aspirational refs): {dep_unresolved}")

# ---- Pass 3: seed client_template_vars defaults ----
print(f"[{CLIENT}] pass 3: seed client_template_vars defaults")
# P2: prefer the interview answer for the CRM platform instead of a blind
# GoHighLevel hardcode. INSERT OR IGNORE below still never clobbers an override.
CRM_PLATFORM = _resolve_crm_platform(CLIENT)
print(f"[{CLIENT}] crm_platform resolved to {CRM_PLATFORM!r} (interview/config-derived; GoHighLevel = fleet default)")
# Verify the GHL PIT BEFORE stamping GoHighLevel so the operator (never the
# client) is told when templates are discoverable but agents can't act on GHL.
if CRM_PLATFORM == "GoHighLevel" and not _ghl_pit_present():
    print(
        f"[{CLIENT}] NOTE (operator): stamping crm_platform='GoHighLevel' but "
        f"GOHIGHLEVEL_API_KEY (PIT) is absent from secrets/.env — GHL funnel/automation "
        f"templates are discoverable yet department agents cannot ACT on GHL until Skill 36 "
        f"wires GOHIGHLEVEL_API_KEY (PIT) + GOHIGHLEVEL_LOCATION_ID. Non-blocking.",
        file=sys.stderr,
    )
DEFAULTS = {
    "crm_platform": CRM_PLATFORM,
    "analytics_platform": "Google Analytics 4",
    "project_management": "Airtable",
    "automation_platform": "N8N",
    "email_platform": "GoHighLevel Email",
    "cloud_storage": "Google Drive",
    "notification_channel": "Telegram",
    "escalation_contact": "owner_email",
    "design_tool": "Canva",
    "scheduling_platform": "Google Calendar",
    "code_repository": "GitHub",
    "billing_platform": "QuickBooks",
    "voice_platform": "Fish Audio",
    "monitoring_service": "UptimeRobot",
    "monitoring_tool": "Datadog",
    "ab_testing_platform": "Google Optimize",
    "payment_processor": "Stripe",
    "social_platforms": "LinkedIn, X, Facebook",
    "heatmap_tool": "Hotjar",
}
ctv_inserted = 0
for var, val in DEFAULTS.items():
    try:
        db.execute(
            "INSERT OR IGNORE INTO client_template_vars (id, client_slug, var_name, var_value, default_value) VALUES (?,?,?,?,?)",
            (secrets.token_hex(8), CLIENT, var, val, val),
        )
        ctv_inserted += 1
    except Exception:
        pass
db.commit()
print(f"  inserted: {ctv_inserted}")

# ---- Verification ----
total = db.execute('SELECT COUNT(*) FROM sops').fetchone()[0]
v2 = db.execute("SELECT COUNT(*) FROM sops WHERE layer_version='v2'").fetchone()[0]
v1 = db.execute("SELECT COUNT(*) FROM sops WHERE layer_version='v1'").fetchone()[0]
deps = db.execute('SELECT COUNT(*) FROM sop_dependencies').fetchone()[0]
ctv = db.execute('SELECT COUNT(*) FROM client_template_vars WHERE client_slug=?', (CLIENT,)).fetchone()[0]
hi = db.execute('SELECT COUNT(*) FROM sops WHERE confidence>=0.85').fetchone()[0]
print(f"[{CLIENT}] verification:")
print(f"  sops total:       {total}")
print(f"  v2 sops:          {v2}")
print(f"  v1 sops:          {v1}")
print(f"  sop_dependencies: {deps}")
print(f"  template vars:    {ctv}")
print(f"  confidence ≥0.85: {hi}")
db.close()
print(f"[{CLIENT}] DONE")
