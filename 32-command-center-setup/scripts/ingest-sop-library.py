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
import sqlite3, json, os, secrets, sys, hashlib
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
        # U119 (same as U078): collision-resistant deterministic identifier. The
        # old 60-char truncation caused 26 collision groups covering 88 slugs,
        # collapsing to 26 surviving identifiers — 62 records silently destroyed
        # (INSERT OR REPLACE on the colliding PRIMARY KEY). A full sha256 hash of
        # the slug is collision-resistant and deterministic, so every distinct
        # slug lands as a distinct row and the canonical count reconciles with the
        # asset's distinct-slug count.
        sop_id = "sop_" + hashlib.sha256(slug.encode()).hexdigest()

        # U119: explicit collision detection — abort rather than silently replace.
        # If this sop_id already exists with a DIFFERENT slug, that's a hash
        # collision (astronomically unlikely with sha256, but checked anyway so a
        # future regression can never silently destroy a record again).
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
