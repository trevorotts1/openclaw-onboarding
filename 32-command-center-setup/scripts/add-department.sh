#!/usr/bin/env bash
# add-department.sh -- add a NEW department to an existing client's Command Center.
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
# PRD 2.11 (dept trio): every department -- including custom departments added
# by this script -- must have a QC Specialist, a Deep Research Specialist, and
# a Devil's Advocate agent row. The Devil's Advocate is AUTO-CREATED and is
# NEVER surfaced to the client (not shown on the board, not mentioned in any
# communication or deliverable). These three rows are created alongside the
# department head on every fresh add-department.sh invocation.
#
# What it does (every step is idempotent -- safe to re-run with the same args):
#   1. INSERT a row into the workspaces table (id = slug)
#   2. INSERT a department-head row into the agents table (status='standby')
#   2b. INSERT a QC Specialist agent row (is_master=0, status='standby')
#   2c. INSERT a Deep Research Specialist agent row (is_master=0, status='standby')
#   2d. INSERT a Devil's Advocate agent row -- AUTO-CREATED, NEVER shown to client
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
#   8. scaffold_agent_files() -- per-agent IDENTITY/SOUL/MEMORY/HEARTBEAT files
#      + shared-file symlinks, written to $OC_ROOT/workspace/departments/<slug>/
#   8b. wire_department_runtime() -- (ROOT-CAUSE FIX, see below) materialize the
#      REAL OpenClaw agent runtime for the new department.
#   9. register_routing_dept() -- routing-extension sidecar ledger entry
#
# THE BUG THIS FIXES (do not let it regress): despite this header's long-
# standing claim that this script does "the full chain in one shot," it NEVER
# actually wired the OpenClaw agent RUNTIME: an openclaw.json agents.list[]
# entry (id=dept-<slug>) plus the $OC_ROOT/agents/dept-<slug>/ directory. The
# workspaces/agents DB rows above make the department SHOW UP on the Command
# Center board; register_routing_dept() only writes a routing-sidecar
# bookkeeping file (extension-registry.json), never agents.list[]. Without the
# real runtime entry, Command Center's dispatch resolves NO specialist for the
# department and every card lands and immediately STICKS in "Blocked" with
# reason no_specialist_runtime -- forever, since nothing here ever creates it.
# This is the exact defect that hit the Anthology (Skill 59) department
# tonight; that skill's own caller (provision-anthology-client.sh) was patched
# with a working wire_department_runtime() step, but THIS shared tool -- used
# by every other skill and by any operator adding a department by hand -- was
# not, so the bug would keep reproducing indefinitely. wire_department_runtime()
# below closes that gap for every caller of add-department.sh, present and
# future, by preferring the real, shared materialize-dept-agents.sh (same
# schema, one source of truth) and falling back to an inline replica (schema
# matched byte-for-byte against materialize-dept-agents.sh /
# 59-anthology-engine's tested wire_department_runtime()) only if that sibling
# script is missing from the install.
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
#   0 -- success (created OR already_exists)
#   1 -- fatal (missing args, missing DB, malformed config, etc.)

set -euo pipefail

# ─── Root guard (config writes as the node user, NEVER root) ─────────────────
# This script mutates mission-control.db, openclaw.json, and role-library
# _index.json. Root writes to those files freeze the gateway / leave
# root-owned files the node user can no longer write (EACCES on client boxes
# thereafter). Mirrors check_root_guard() in
# 59-anthology-engine/scripts/provision-anthology-client.sh.
if [[ "$(id -u)" == "0" ]]; then
  echo "[add-department] FATAL: refusing to run as root -- config writes must be the node user (root writes freeze the gateway / EACCES on client boxes). Re-run as the node user, e.g. sudo -u node bash add-department.sh ..." >&2
  exit 1
fi

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

# Normalize slug -- lowercase, hyphens only
SLUG_NORM=$(echo "$SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
if [[ -z "$SLUG_NORM" ]]; then
  echo "[add-department] FATAL: slug normalized to empty -- provide a valid slug" >&2
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
  echo "[add-department] FATAL: python3 not on PATH -- required" >&2
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
            print("[add-department] FATAL: workspaces table missing -- run seed-workspaces.py first", file=sys.stderr)
            sys.exit(1)
        if not ag_cols or not tk_cols:
            print("[add-department] FATAL: agents/tasks table missing -- dashboard schema mismatch", file=sys.stderr)
            sys.exit(1)

        # ─── Idempotency: if slug already a workspace, short-circuit ────────
        existing = db.execute(
            "SELECT id FROM workspaces WHERE slug = ? OR id = ? LIMIT 1",
            (SLUG, SLUG),
        ).fetchone()
        if existing:
            ws_id = existing[0]
            print(f"[add-department] workspace already exists: id={ws_id}")
            # Heal idempotently: role-library, per-agent file scaffold, persona-
            # stale, RUNTIME WIRING, and routing. (routing may have been missing
            # if this dept was created before the G3 fix; the runtime may be
            # missing if this dept was created before the no_specialist_runtime
            # fix below -- re-running add-department.sh on ANY existing
            # department now self-heals it onto the real OpenClaw runtime.)
            upsert_role_library(SLUG, NAME)
            scaffold_agent_files(SLUG, HEAD_NAME)
            mark_persona_stale()
            runtime_status = wire_department_runtime(SLUG, HEAD_NAME)
            register_routing_dept(SLUG)
            emit_summary({
                "slug": SLUG,
                "workspace_id": ws_id,
                "status": "already_exists",
                "runtime_status": runtime_status,
            })
            if runtime_status == "wiring_failed":
                sys.exit(1)
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
        qc_name = f"QC Specialist -- {NAME}"
        qc_data = {
            "id": qc_agent_id,
            "workspace_id": ws_id,
            "name": qc_name,
            "role": f"QC Specialist",
            # role_type is the CANONICAL lowercase token, NOT the human label.
            # The CC QC scorer resolves the per-dept QC gate via
            # agents.role_type = 'qc' (qc-scorer.ts; column added by migration 060).
            # A human label here ("QC Specialist") silently fails that lookup and
            # the dept degrades to heuristic QC. Canonical tokens match the role
            # library set: specialist, leadership, qc, deep-research, on-call,
            # orchestrator, healer.
            "role_type": "qc",
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
        research_name = f"Deep Research Specialist -- {NAME}"
        research_data = {
            "id": research_agent_id,
            "workspace_id": ws_id,
            "name": research_name,
            "role": "Deep Research Specialist",
            # Canonical lowercase token (see QC note above): the role library uses
            # 'deep-research', not the human label "Deep Research Specialist".
            "role_type": "deep-research",
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
        # AUTO-CREATED. NEVER surfaced to the client -- not shown on the board,
        # not mentioned in any client-facing communication or deliverable.
        # Surfaces blind spots in high-stakes {dept} work before it ships.
        # Triggers on: critical tasks, strategic decisions, consecutive approvals,
        # and KPI swings > 20%. Runs silently in the background.
        da_agent_id = secrets.token_hex(8)
        da_name = f"Devil's Advocate -- {NAME}"
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
        print(f"  + agent (DA)     {da_agent_id}  ({da_name}) [INTERNAL -- never shown to client]")

        # --- 2e. (PRD 2.11+healer) INSERT Healer agent -----------------------
        # Every department gets a Healer (department immune system).
        # Receives: second consecutive stall handoffs from the watchdog,
        # QC loop-4 escalations, API failCode events, and operator bug reports.
        # role_type: healer (canonical lowercase value).
        healer_agent_id = secrets.token_hex(8)
        healer_name = f"Healer -- {NAME}"
        healer_data = {
            "id": healer_agent_id,
            "workspace_id": ws_id,
            "name": healer_name,
            "role": "Healer",
            "role_type": "healer",
            "persona": f"healer-{SLUG}",
            "description": (
                f"Department immune system for the {NAME} department. "
                f"Receives watchdog stall handoffs, QC loop-4 escalations, "
                f"and API failCode events. Diagnoses root cause, fixes the run, "
                f"and patches the SOP so the same failure never recurs."
            ),
            "specialist_type": "permanent",
            "status": "standby",
            "avatar_emoji": "🩹",
            "is_master": 0,
            "created_at": NOW,
            "updated_at": NOW,
        }
        insert_cols = [c for c in healer_data if c in ag_cols]
        sql = f"INSERT INTO agents ({','.join(insert_cols)}) VALUES ({','.join('?'*len(insert_cols))})"
        db.execute(sql, [healer_data[c] for c in insert_cols])
        print(f"  + agent (Healer) {healer_agent_id}  ({healer_name})")

        # --- 3. INSERT starter task ──────────────────────────────────────────
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
    # Subagents excluded -- Skill 23 handles those.
    scaffold_agent_files(SLUG, HEAD_NAME)

    # ─── 8b. (ROOT-CAUSE FIX) Materialize the OpenClaw agent RUNTIME ──────────
    # See the header comment above ("THE BUG THIS FIXES"). scaffold_agent_files()
    # just above already created $OC_ROOT/workspace/departments/<slug>/ -- the
    # exact folder materialize-dept-agents.sh's department scanner looks for --
    # so calling it now lets the new department's runtime be discovered and
    # wired in the SAME pass, using the one shared schema.
    runtime_status = wire_department_runtime(SLUG, HEAD_NAME)

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
        "runtime_status": runtime_status,
        "status": "created",
    })
    if runtime_status == "wiring_failed":
        sys.exit(1)


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
        print(f"  [role-library] _index.json not found in any expected location -- skipping")
        return False

    try:
        idx = json.load(open(target))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [role-library] WARN failed to read {target}: {e}", file=sys.stderr)
        return False

    deps = idx.setdefault("departments", {})
    head_slug = f"head-of-{slug}"

    if slug in deps:
        # Already present -- make sure the head role is in the list
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

    # Recompute totals so _index.json stays internally consistent (§1.1b fix)
    idx["total_roles"] = sum(len(d.get("roles", [])) for d in deps.values())
    idx["total_departments"] = len(deps)

    # Refresh generated-at timestamp
    idx["generated_at"] = NOW
    try:
        import tempfile
        idx_dir = target.parent
        fd, tmp_path = tempfile.mkstemp(prefix=".idx.", suffix=".json.tmp", dir=str(idx_dir))
        with os.fdopen(fd, "w") as f:
            json.dump(idx, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(target))
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

    # Idempotent -- don't double-add
    for b in bindings:
        if isinstance(b, dict) and b.get("agent_id") == agent_id:
            print(f"  [openclaw.json] telegram binding for {agent_id} already present, no change")
            return

    bindings.append({
        "topic_id": None,  # operator fills in
        "agent_id": agent_id,
        "label": name,
        "_note": "Added by add-department.sh -- operator must set topic_id",
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
    Best-effort -- never fails the parent."""
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
    agent. Best-effort -- never fails the parent.

    Sub-agents (role folders inside this dept) are NOT scaffolded here -- they
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


def wire_department_runtime(slug, head_name):
    """(ROOT-CAUSE FIX) Materialize the REAL OpenClaw agent runtime for this
    department: the openclaw.json agents.list[] entry (id=dept-<slug>) AND the
    $OC_ROOT/agents/dept-<slug>/ directory. Command Center's dispatch resolves
    a specialist for a department via THAT runtime -- not the workspaces/
    agents DB rows inserted above, and not the routing sidecar
    register_routing_dept() writes. Without it, every card for this
    department lands and immediately STICKS in "Blocked" with reason
    no_specialist_runtime, forever.

    Prefers calling the REAL, shared materialize-dept-agents.sh so the
    runtime schema has exactly one source of truth. materialize-dept-agents.sh
    has no --dept flag (it is a batch scanner over all department folders on
    disk), but it is documented idempotent for every department it finds, so
    re-running it here -- now that scaffold_agent_files() has just created
    $OC_ROOT/workspace/departments/<slug>/, one of the folders it scans -- is
    safe and heals any other previously-unwired department in the same pass.

    Falls back to an inline replica of the exact same schema (id, name,
    workspace, agentDir, memorySearch: multimodal disabled + fallback openai)
    ONLY if materialize-dept-agents.sh is missing from this install, so a
    broken/absent sibling script never leaves a department unwired. This
    schema is matched byte-for-byte against materialize-dept-agents.sh AND
    against the tested, working wire_department_runtime() in
    59-anthology-engine/scripts/provision-anthology-client.sh (tonight's fix
    for the same bug, scoped to its one caller).

    Returns one of:
      "wired"                         -- agents.list[] entry + agent dir confirmed present (read-back verified)
      "deferred_interview_incomplete" -- materialize-dept-agents.sh's own precondition (the AI Workforce
                                          interview not marked complete yet) deferred materialization;
                                          re-run add-department.sh (or materialize-dept-agents.sh) once it is
      "no_openclaw_json"              -- openclaw.json not found under OC_ROOT; nothing to wire yet
      "wiring_failed"                 -- wiring was attempted but the read-back check still failed
    """
    cfg_path = Path(OC_ROOT) / "openclaw.json"
    if not cfg_path.is_file():
        print(f"  [runtime] openclaw.json not found at {cfg_path} -- cannot wire dept-{slug} runtime, skipping",
              file=sys.stderr)
        return "no_openclaw_json"

    agent_id = f"dept-{slug}"
    agent_dir = Path(OC_ROOT) / "agents" / agent_id

    def _runtime_present():
        try:
            cfg = json.load(open(cfg_path))
        except (json.JSONDecodeError, OSError):
            return False
        agents_list = cfg.get("agents", {}).get("list", []) if isinstance(cfg.get("agents"), dict) else []
        has_entry = any(isinstance(a, dict) and a.get("id") == agent_id for a in agents_list)
        return has_entry and agent_dir.is_dir()

    materializer = Path(SCRIPT_DIR) / "materialize-dept-agents.sh"
    if materializer.is_file():
        try:
            result = subprocess.run(
                ["bash", str(materializer)],
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"  [runtime] WARN: materialize-dept-agents.sh failed to run: {e}", file=sys.stderr)
            result = None

        if result is not None:
            combined_out = (result.stdout or "") + (result.stderr or "")
            if "INTERVIEW_NOT_COMPLETE" in combined_out:
                print(f"  [runtime] materialize-dept-agents.sh deferred: the AI Workforce interview "
                      f"is not marked complete yet for this client. dept-{slug}'s board card will show "
                      f"Blocked (no_specialist_runtime) until the interview finishes and add-department.sh "
                      f"(or materialize-dept-agents.sh) is re-run.", file=sys.stderr)
                return "deferred_interview_incomplete"
            if result.returncode != 0:
                print(f"  [runtime] WARN: materialize-dept-agents.sh exited rc={result.returncode}: "
                      f"{result.stderr.strip()[:400]}", file=sys.stderr)
            else:
                print(f"  ~ runtime         materialize-dept-agents.sh ran (batch pass; idempotent for "
                      f"every department it finds)")

        if _runtime_present():
            print(f"  + runtime         dept-{slug} wired: agents.list[] entry + {agent_dir} "
                  f"(read-back verified)")
            return "wired"
        print(f"  [runtime] WARN: materialize-dept-agents.sh ran but read-back still shows no "
              f"agents.list[] entry / dir for {agent_id} -- falling back to inline wiring", file=sys.stderr)
    else:
        print(f"  [runtime] materialize-dept-agents.sh not found at {materializer} -- "
              f"falling back to inline runtime wiring", file=sys.stderr)

    # ─── Inline fallback: replicate materialize-dept-agents.sh's exact schema ──
    try:
        cfg = json.load(open(cfg_path))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [runtime] FATAL: cannot read {cfg_path}: {e}", file=sys.stderr)
        return "wiring_failed"

    if not isinstance(cfg.get("agents"), dict):
        cfg["agents"] = {"list": []}
    if not isinstance(cfg["agents"].get("list"), list):
        cfg["agents"]["list"] = []

    workspace_path = str(Path(OC_ROOT) / "workspace" / "departments" / slug)
    desired_entry = {
        "id": agent_id,
        "name": head_name,
        "workspace": workspace_path,
        "agentDir": str(agent_dir),
        "memorySearch": {
            "extraPaths": [],
            "multimodal": {"enabled": False, "modalities": []},
            "fallback": "openai",
        },
    }
    agent_list = cfg["agents"]["list"]
    by_id = {a.get("id"): a for a in agent_list if isinstance(a, dict) and a.get("id")}
    existing_entry = by_id.get(agent_id)
    if existing_entry is None:
        agent_list.append(desired_entry)
    else:
        for k in ("name", "workspace", "agentDir"):
            if existing_entry.get(k) != desired_entry[k]:
                existing_entry[k] = desired_entry[k]
        existing_entry.setdefault("memorySearch", desired_entry["memorySearch"])

    # Backup (best-effort) + atomic write. Never as root -- the bash guard at
    # the top of this script already refused a root invocation before this
    # python heredoc ever started.
    try:
        backups_dir = Path(OC_ROOT) / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (backups_dir / f"openclaw-backup-{ts}-pre-wire-{slug}.json").write_text(
            cfg_path.read_text(), encoding="utf-8")
    except OSError:
        pass  # backup is best-effort

    try:
        import tempfile
        cfg_dir = cfg_path.parent
        fd, tmp_path = tempfile.mkstemp(prefix=".openclaw.", suffix=".json.tmp", dir=str(cfg_dir))
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(cfg_path))
    except OSError as e:
        print(f"  [runtime] FATAL: atomic write of {cfg_path} failed: {e}", file=sys.stderr)
        return "wiring_failed"

    agent_dir.mkdir(parents=True, exist_ok=True)

    if _runtime_present():
        print(f"  + runtime         dept-{slug} wired via inline fallback: agents.list[] entry + "
              f"{agent_dir} (read-back verified)")
        return "wired"

    print(f"  [runtime] FATAL: wiring attempted but read-back STILL shows no runtime for {agent_id}",
          file=sys.stderr)
    return "wiring_failed"


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
    inserting). Best-effort -- never fails the parent."""
    oc_json = Path(OC_ROOT) / "openclaw.json"
    register_py = Path(SCRIPT_DIR) / "register-routing-dept.py"
    if not register_py.is_file():
        print(f"  [routing] register-routing-dept.py not found at {register_py} -- skipping",
              file=sys.stderr)
        return
    if not oc_json.is_file():
        print(f"  [routing] openclaw.json not found at {oc_json} -- skipping",
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
