#!/usr/bin/env bash
# add-department.sh — add a NEW department to an existing client's Command Center.
#
# Background:
#   v10.14.26 ships seed-workspaces.py + seed-dashboard-content.py + materialize-
#   dept-agents.sh, all of which run during the initial install. But once a
#   client is live, there is NO script that lets Trevor (or the client) add a
#   brand-new department after the fact. Adding "Podcast Production" to a live
#   Command Center required hand-editing the SQLite DB, manually adding a
#   role-library entry, manually editing openclaw.json bindings, and re-running
#   generate-brand-css.py. This script does the full chain in one shot.
#
# PRD 2.11 (dept trio): every department — including custom departments added
# by this script — must have a QC Specialist, a Deep Research Specialist, and
# a Devil's Advocate agent row. The Devil's Advocate is AUTO-CREATED and is
# NEVER surfaced to the client (not shown on the board, not mentioned in any
# communication or deliverable). These three rows are created alongside the
# department head on every fresh add-department.sh invocation.
#
# What it does (every step is idempotent — safe to re-run with the same args):
#   1. INSERT a row into the workspaces table (id = slug)
#   2. INSERT a department-head row into the agents table (status='standby')
#   2b. INSERT a QC Specialist agent row (is_master=0, status='standby')
#   2c. INSERT a Deep Research Specialist agent row (is_master=0, status='standby')
#   2d. INSERT a Devil's Advocate agent row — AUTO-CREATED, NEVER shown to client
#   3. INSERT a starter "Welcome to <Dept>" task into the tasks table
#      (status='backlog', assigned/created_by = the head agent's id)
#   4. Append the new dept slug to 23-ai-workforce-blueprint/templates/role-
#      library/_index.json under departments.<slug> = {count:1, roles:[head-...]}
#   5. If openclaw.json has telegram bindings, append a new binding entry
#      mapping the new dept to a placeholder topic id (operator fills in later)
#   6. Re-run generate-brand-css.py so any dept-specific styling lands
#   7. Drop /data/.openclaw/skills/23-ai-workforce-blueprint/.persona-index-stale
#      so persona-selector-v2.py knows to rebuild any cached dept-tag → persona
#      map next run (no-op if selector doesn't have caching today)
#
# Usage:
#   bash add-department.sh --slug podcast --name "Podcast Production"
#   bash add-department.sh --slug podcast --name "Podcast Production" \
#     --icon 🎙️ --head-name "Podcast Lead" --description "..."
#
# Output: prints human-readable progress, then a single JSON line at the end:
#   {"slug":"podcast","workspace_id":"podcast","head_agent_id":"abcd1234",
#    "starter_task_id":"efgh5678","status":"created"}
# or:
#   {"slug":"podcast","status":"already_exists"}
#
# Exit codes:
#   0 — success (created OR already_exists)
#   1 — fatal (missing args, missing DB, malformed config, etc.)

set -euo pipefail

# ─── Arg parsing ─────────────────────────────────────────────────────────────
SLUG=""
NAME=""
ICON=""
HEAD_NAME=""
DESCRIPTION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slug)         SLUG="${2:-}";        shift 2 ;;
    --name)         NAME="${2:-}";        shift 2 ;;
    --icon)         ICON="${2:-}";        shift 2 ;;
    --head-name)    HEAD_NAME="${2:-}";   shift 2 ;;
    --description)  DESCRIPTION="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,40p' "$0"
      exit 0
      ;;
    *)
      echo "[add-department] FATAL: unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SLUG" || -z "$NAME" ]]; then
  echo "[add-department] FATAL: --slug and --name are required" >&2
  echo "Usage: bash add-department.sh --slug X --name \"Y\" [--icon 🔧] [--head-name \"Z Lead\"] [--description \"...\"]" >&2
  exit 1
fi

# Normalize slug — lowercase, hyphens only
SLUG_NORM=$(echo "$SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
if [[ -z "$SLUG_NORM" ]]; then
  echo "[add-department] FATAL: slug normalized to empty — provide a valid slug" >&2
  exit 1
fi
SLUG="$SLUG_NORM"

# Defaults derived from --name
[[ -z "$ICON" ]] && ICON="📁"
[[ -z "$HEAD_NAME" ]] && HEAD_NAME="$NAME Lead"
[[ -z "$DESCRIPTION" ]] && DESCRIPTION="$NAME department workspace"

# ─── Platform detection (mirror materialize-dept-agents.sh) ──────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[add-department] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[add-department] FATAL: python3 not on PATH — required" >&2
  exit 1
fi

# Discover the DB (mirror seed-workspaces.py find_db())
DB_PATH=""
for cand in \
  "$HOME/projects/command-center/mission-control.db" \
  "$HOME/projects/mission-control/mission-control.db" \
  "/opt/mission-control/mission-control.db" \
  "/app/mission-control.db" \
  "/data/projects/command-center/mission-control.db"
do
  if [[ -f "$cand" ]]; then
    DB_PATH="$cand"
    break
  fi
done

if [[ -z "$DB_PATH" ]]; then
  echo "[add-department] FATAL: mission-control.db not found in any of the expected locations" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[add-department] OC_ROOT=$OC_ROOT"
echo "[add-department] DB=$DB_PATH"
echo "[add-department] slug=$SLUG name=$NAME icon=$ICON head=$HEAD_NAME"

# ─── All mutation happens in one Python heredoc (no bash JSON acrobatics) ───
export AD_DB_PATH="$DB_PATH"
export AD_SLUG="$SLUG"
export AD_NAME="$NAME"
export AD_ICON="$ICON"
export AD_HEAD_NAME="$HEAD_NAME"
export AD_DESCRIPTION="$DESCRIPTION"
export AD_OC_ROOT="$OC_ROOT"
export AD_SCRIPT_DIR="$SCRIPT_DIR"

python3 <<'PYEOF'
import json
import os
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH       = os.environ["AD_DB_PATH"]
SLUG          = os.environ["AD_SLUG"]
NAME          = os.environ["AD_NAME"]
ICON          = os.environ["AD_ICON"]
HEAD_NAME     = os.environ["AD_HEAD_NAME"]
DESCRIPTION   = os.environ["AD_DESCRIPTION"]
OC_ROOT       = os.environ["AD_OC_ROOT"]
SCRIPT_DIR    = os.environ["AD_SCRIPT_DIR"]

NOW = datetime.now(timezone.utc).isoformat()


def emit_summary(payload):
    """Final JSON-shaped summary line (machine-readable)."""
    print("---SUMMARY---")
    print(json.dumps(payload, separators=(",", ":")))


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        ws_cols = [r[1] for r in db.execute("PRAGMA table_info(workspaces)")]
        ag_cols = [r[1] for r in db.execute("PRAGMA table_info(agents)")]
        tk_cols = [r[1] for r in db.execute("PRAGMA table_info(tasks)")]
        if not ws_cols:
            print("[add-department] FATAL: workspaces table missing — run seed-workspaces.py first", file=sys.stderr)
            sys.exit(1)
        if not ag_cols or not tk_cols:
            print("[add-department] FATAL: agents/tasks table missing — dashboard schema mismatch", file=sys.stderr)
            sys.exit(1)

        # ─── Idempotency: if slug already a workspace, short-circuit ────────
        existing = db.execute(
            "SELECT id FROM workspaces WHERE slug = ? OR id = ? LIMIT 1",
            (SLUG, SLUG),
        ).fetchone()
        if existing:
            ws_id = existing[0]
            print(f"[add-department] workspace already exists: id={ws_id}")
            # Heal idempotently: role-library, persona-stale, and routing
            # (routing may have been missing if this dept was created before G3 fix)
            upsert_role_library(SLUG, NAME)
            mark_persona_stale()
            register_routing_dept(SLUG)
            emit_summary({"slug": SLUG, "workspace_id": ws_id, "status": "already_exists"})
            return

        # ─── 1. INSERT workspaces row (id == slug, per the schema convention) ──
        ws_id = SLUG
        max_order = db.execute("SELECT MAX(sort_order) FROM workspaces").fetchone()[0]
        next_order = (max_order or 0) + 10

        ws_data = {
            "id": ws_id,
            "name": NAME,
            "slug": SLUG,
            "description": DESCRIPTION,
            "icon": ICON,
            "parent": "company",
            "sort_order": next_order,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in ws_data if c in ws_cols]
        sql = f"INSERT INTO workspaces ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [ws_data[c] for c in insert_cols])
        print(f"  + workspace      {ws_id}  (sort_order={next_order})")

        # ─── 2. INSERT department-head agent ─────────────────────────────────
        head_agent_id = secrets.token_hex(8)
        ag_data = {
            "id": head_agent_id,
            "workspace_id": ws_id,
            "name": HEAD_NAME,
            "role": f"{NAME} Department Head",
            "persona": f"dept-{SLUG}",
            "description": f"Heads the {NAME} department in your AI workforce.",
            "specialist_type": "permanent",
            "status": "standby",  # CHECK constraint: standby | working | offline
            "avatar_emoji": ICON,
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in ag_data if c in ag_cols]
        sql = f"INSERT INTO agents ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [ag_data[c] for c in insert_cols])
        print(f"  + agent          {head_agent_id}  ({HEAD_NAME})")

        # ─── 2b. (G3 fix) INSERT dedicated QC specialist agent ───────────────
        # The per-dept QC gate (built CC-side) needs an agent row to resolve to.
        # Without this row, the CC QC gate has no agent and the dept is effectively
        # unverifiable. Idempotent: the workspaces idempotency guard above means
        # we only reach here on a fresh INSERT, so this is always safe.
        qc_agent_id = secrets.token_hex(8)
        qc_name = f"QC Specialist — {NAME}"
        qc_data = {
            "id": qc_agent_id,
            "workspace_id": ws_id,
            "name": qc_name,
            "role": f"QC Specialist",
            "role_type": "QC Specialist",
            "persona": f"qc-specialist-{SLUG}",
            "description": f"Quality control gate for the {NAME} department. Reviews all deliverables before sign-off.",
            "specialist_type": "permanent",
            "status": "standby",
            "avatar_emoji": "🔍",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in qc_data if c in ag_cols]
        sql = f"INSERT INTO agents ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [qc_data[c] for c in insert_cols])
        print(f"  + agent (QC)     {qc_agent_id}  ({qc_name})")

        # ─── 2c. (PRD 2.11) INSERT Deep Research Specialist agent ────────────
        # Every department gets a research specialist so the Devil's Advocate and
        # other specialists have a dedicated research resource. Auto-created.
        research_agent_id = secrets.token_hex(8)
        research_name = f"Deep Research Specialist — {NAME}"
        research_data = {
            "id": research_agent_id,
            "workspace_id": ws_id,
            "name": research_name,
            "role": "Deep Research Specialist",
            "role_type": "Deep Research Specialist",
            "persona": f"deep-research-specialist-{SLUG}",
            "description": (
                f"Deep research intelligence engine for the {NAME} department. "
                f"Provides Tier-1-cited research (McKinsey, HBR, IBISWorld, Statista) "
                f"for all {NAME.lower()} decisions."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            "avatar_emoji": "🔬",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in research_data if c in ag_cols]
        sql = f"INSERT INTO agents ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [research_data[c] for c in insert_cols])
        print(f"  + agent (Research) {research_agent_id}  ({research_name})")

        # ─── 2d. (PRD 2.11) INSERT Devil's Advocate agent ────────────────────
        # AUTO-CREATED. NEVER surfaced to the client — not shown on the board,
        # not mentioned in any client-facing communication or deliverable.
        # Surfaces blind spots in high-stakes {dept} work before it ships.
        # Triggers on: critical tasks, strategic decisions, consecutive approvals,
        # and KPI swings > 20%. Runs silently in the background.
        da_agent_id = secrets.token_hex(8)
        da_name = f"Devil's Advocate — {NAME}"
        da_data = {
            "id": da_agent_id,
            "workspace_id": ws_id,
            "name": da_name,
            "role": "Devil's Advocate",
            "role_type": "devils-advocate",
            "persona": f"devils-advocate-{SLUG}",
            "description": (
                f"Internal challenge mechanism for the {NAME} department. "
                f"Auto-created. NEVER surfaced to the client. Surfaces blind "
                f"spots in high-stakes decisions before they cause real-world damage."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            # Hidden from client-facing views: avatar_emoji omitted intentionally
            # so the board filter (emoji != null) can suppress it if desired.
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in da_data if c in ag_cols]
        sql = f"INSERT INTO agents ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [da_data[c] for c in insert_cols])
        print(f"  + agent (DA)     {da_agent_id}  ({da_name}) [INTERNAL — never shown to client]")

        # ─── 3. INSERT starter task ──────────────────────────────────────────
        task_id = secrets.token_hex(8)
        tk_data = {
            "id": task_id,
            "workspace_id": ws_id,
            "department": SLUG,
            "title": f"Welcome to {NAME}",
            "description": (
                f"This is your {NAME} department's first task. "
                f"Click to edit. Your AI workforce will populate real "
                f"tasks as work comes in."
            ),
            "status": "backlog",
            "priority": "medium",
            "assigned_agent_id": head_agent_id,
            "created_by_agent_id": head_agent_id,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in tk_data if c in tk_cols]
        sql = f"INSERT INTO tasks ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [tk_data[c] for c in insert_cols])
        print(f"  + task           {task_id}  (Welcome to {NAME})")

        db.commit()
    finally:
        db.close()

    # ─── 4. Role-library _index.json upsert ──────────────────────────────────
    upsert_role_library(SLUG, NAME)

    # ─── 5. openclaw.json bindings (append topic binding if structure exists) ─
    append_telegram_binding(SLUG, NAME)

    # ─── 6. Re-run generate-brand-css.py ────────────────────────────────────
    regen_brand_css()

    # ─── 7. Persona-selector re-index hint ──────────────────────────────────
    mark_persona_stale()

    # ─── 8. Per-agent file scaffold (Trevor's agent-file architecture v10.14.29) ─
    # SHARED across all agents: USER.md, AGENTS.md, TOOLS.md (workspace root)
    # PER-AGENT: IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md (dept folder)
    # Subagents excluded — Skill 23 handles those.
    scaffold_agent_files(SLUG, HEAD_NAME)

    # ─── 9. (G3 fix) Register routing entry in openclaw.json ─────────────────
    # add-department.sh previously wrote the CC workspaces row + agent but
    # never called register-routing-dept.py → the dept existed in the CC board
    # but messages were never routed there because openclaw.json had no routing
    # entry. Now register routing idempotently for the manual path too.
    register_routing_dept(SLUG)

    emit_summary({
        "slug": SLUG,
        "workspace_id": ws_id,
        "head_agent_id": head_agent_id,
        "qc_agent_id": qc_agent_id,
        "research_agent_id": research_agent_id,
        "da_agent_id": da_agent_id,
        "starter_task_id": task_id,
        "status": "created",
    })


def upsert_role_library(slug, name):
    """Add the new dept (or update its head-role marker) in the role-library
    _index.json. Returns True if file changed, False if already in sync."""
    # The role library lives in the installer's static skill payload. Try the
    # installed-skills path first (live VPS), then fall back to the repo path
    # (so this is usable from the repo too during dev/testing).
    candidates = [
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"),
        Path.home() / ".openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json",
        Path(SCRIPT_DIR).resolve().parent.parent / "23-ai-workforce-blueprint/templates/role-library/_index.json",
    ]
    target = None
    for p in candidates:
        if p.is_file():
            target = p
            break
    if not target:
        print(f"  [role-library] _index.json not found in any expected location — skipping")
        return False

    try:
        idx = json.load(open(target))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [role-library] WARN failed to read {target}: {e}", file=sys.stderr)
        return False

    deps = idx.setdefault("departments", {})
    head_slug = f"head-of-{slug}"

    if slug in deps:
        # Already present — make sure the head role is in the list
        roles = deps[slug].get("roles", [])
        if head_slug not in roles:
            roles.append(head_slug)
            roles.sort()
            deps[slug]["roles"] = roles
            deps[slug]["count"] = len(roles)
        else:
            print(f"  [role-library] dept '{slug}' already present, no change")
            return False
    else:
        deps[slug] = {"count": 1, "roles": [head_slug]}
        print(f"  + role-library   added dept '{slug}' with [{head_slug}]")

    # Refresh generated-at timestamp
    idx["generated_at"] = NOW
    try:
        with open(target, "w") as f:
            json.dump(idx, f, indent=2)
            f.write("\n")
        return True
    except OSError as e:
        print(f"  [role-library] WARN failed to write {target}: {e}", file=sys.stderr)
        return False


def append_telegram_binding(slug, name):
    """If openclaw.json has a telegram bindings array, append a new binding for
    this dept. Skip gracefully if no bindings shape is found."""
    cfg_path = Path(OC_ROOT) / "openclaw.json"
    if not cfg_path.is_file():
        print(f"  [openclaw.json] not found at {cfg_path}, skipping")
        return

    try:
        cfg = json.load(open(cfg_path))
    except json.JSONDecodeError as e:
        print(f"  [openclaw.json] WARN malformed JSON: {e}", file=sys.stderr)
        return

    # The shape we look for: cfg["agents"]["list"][i]["telegram"]["bindings"]
    # is an array of {topic_id, agent_id} entries. We won't invent a topic_id
    # (operator must wire that), but we WILL add a placeholder binding so the
    # operator sees the slot exists.
    agents_list = cfg.get("agents", {}).get("list", []) if isinstance(cfg.get("agents"), dict) else []
    if not isinstance(agents_list, list):
        print(f"  [openclaw.json] no agents.list array found, skipping bindings update")
        return

    # Look for any existing binding shape to learn the schema
    found_bindings_owner = None
    for a in agents_list:
        if isinstance(a, dict) and isinstance(a.get("telegram"), dict):
            if isinstance(a["telegram"].get("bindings"), list):
                found_bindings_owner = a
                break

    if not found_bindings_owner:
        print(f"  [openclaw.json] no telegram.bindings array exists on any agent; skipping (operator may add later)")
        return

    bindings = found_bindings_owner["telegram"]["bindings"]
    agent_id = f"dept-{slug}"

    # Idempotent — don't double-add
    for b in bindings:
        if isinstance(b, dict) and b.get("agent_id") == agent_id:
            print(f"  [openclaw.json] telegram binding for {agent_id} already present, no change")
            return

    bindings.append({
        "topic_id": None,  # operator fills in
        "agent_id": agent_id,
        "label": name,
        "_note": "Added by add-department.sh — operator must set topic_id",
    })

    # Atomic write
    import tempfile
    cfg_dir = cfg_path.parent
    fd, tmp = tempfile.mkstemp(prefix=".openclaw.", suffix=".json.tmp", dir=str(cfg_dir))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp, str(cfg_path))
        print(f"  + openclaw.json  appended telegram binding placeholder for {agent_id}")
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"  [openclaw.json] WARN write failed: {e}", file=sys.stderr)


def regen_brand_css():
    """Re-run generate-brand-css.py so any dept-specific styling lands.
    Best-effort — never fails the parent."""
    script = Path(SCRIPT_DIR) / "generate-brand-css.py"
    if not script.is_file():
        print(f"  [brand-css] {script} not found, skipping")
        return
    try:
        result = subprocess.run(
            ["python3", str(script)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            print(f"  ~ brand.css      regenerated")
        else:
            print(f"  [brand-css] generator exited rc={result.returncode}: {result.stderr.strip()[:200]}",
                  file=sys.stderr)
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  [brand-css] WARN regeneration failed: {e}", file=sys.stderr)


def scaffold_agent_files(slug, head_name):
    """Invoke scaffold-agent-files.sh to write per-agent IDENTITY/SOUL/MEMORY/
    HEARTBEAT and (re)create USER/AGENTS/TOOLS symlinks for the new dept-head
    agent. Best-effort — never fails the parent.

    Sub-agents (role folders inside this dept) are NOT scaffolded here — they
    are excluded from Trevor's agent-file architecture spec (they inherit from
    the dept head)."""
    scaffolder = Path(SCRIPT_DIR) / "scaffold-agent-files.sh"
    if not scaffolder.is_file():
        print(f"  [scaffold] {scaffolder} not found, skipping per-agent file scaffold")
        return
    try:
        result = subprocess.run(
            ["bash", str(scaffolder),
             "--agent-slug", slug,
             "--agent-name", head_name,
             "--department", slug],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"  ~ scaffold       per-agent files written for dept-{slug}")
        else:
            print(f"  [scaffold] WARN: scaffolder exited rc={result.returncode}: "
                  f"{result.stderr.strip()[:300]}", file=sys.stderr)
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  [scaffold] WARN: scaffolder failed: {e}", file=sys.stderr)


def mark_persona_stale():
    """Drop a marker file so persona-selector-v2.py knows to rebuild any
    cached dept-tag → persona map next run. No-op if selector dir absent."""
    candidates = [
        Path("/data/.openclaw/skills/23-ai-workforce-blueprint"),
        Path.home() / ".openclaw/skills/23-ai-workforce-blueprint",
    ]
    for d in candidates:
        if d.is_dir():
            marker = d / ".persona-index-stale"
            try:
                marker.write_text(NOW + "\n")
                print(f"  ~ persona-stale  {marker}")
                return
            except OSError as e:
                print(f"  [persona-stale] WARN {marker}: {e}", file=sys.stderr)
    print(f"  [persona-stale] skill 23 dir not present on disk; no-op")


def register_routing_dept(slug):
    """(G3 fix) Call register-routing-dept.py so openclaw.json gets a routing
    entry for this department. Without this, the CC board shows the dept but
    owner messages are never routed there (the routing universe is openclaw.json,
    NOT the workspaces table).

    Idempotent: register-routing-dept.py itself is idempotent (it checks before
    inserting). Best-effort — never fails the parent."""
    oc_json = Path(OC_ROOT) / "openclaw.json"
    register_py = Path(SCRIPT_DIR) / "register-routing-dept.py"
    if not register_py.is_file():
        print(f"  [routing] register-routing-dept.py not found at {register_py} — skipping",
              file=sys.stderr)
        return
    if not oc_json.is_file():
        print(f"  [routing] openclaw.json not found at {oc_json} — skipping",
              file=sys.stderr)
        return
    try:
        result = subprocess.run(
            ["python3", str(register_py), "--dept", slug, "--config", str(oc_json)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            print(f"  ~ routing        registered dept '{slug}' in openclaw.json")
        else:
            print(f"  [routing] WARN: register-routing-dept.py exited rc={result.returncode}: "
                  f"{result.stderr.strip()[:300]}", file=sys.stderr)
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  [routing] WARN: routing registration failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
PYEOF

RC=$?
if [[ $RC -ne 0 ]]; then
  echo "[add-department] FATAL: python mutation failed (rc=$RC)" >&2
  exit $RC
fi

exit 0
