#!/usr/bin/env bash
# apply-routing-fix.sh — Idempotent 4-layer routing-defect fix for every OpenClaw box.
#
# Bakes the permanent fix for the "master agent builds inline instead of routing to
# departments" defect. All four layers MUST pass before a box is considered routing-clean.
#
# LAYER 1 — DOCTRINE INTO THE CORRECT AGENTS.MD
#   Resolves the main agent's ACTUAL workspace from openclaw.json (per-agent workspace
#   override first, then agents.defaults.workspace, then the canonical default) and
#   injects ROLE_DISCIPLINE_V1 + CEO_ROUTING_NO_LOOPHOLES_V1 into THAT file's AGENTS.md,
#   plus the PRIME DIRECTIVE into its SOUL.md. The prior bug wrote doctrine to
#   ~/clawd/AGENTS.md while the agent read from ~/.openclaw/workspace/AGENTS.md.
#
# LAYER 2 — STRUCTURAL PPTX DENY
#   Sets skills:[] on the main agent in openclaw.json so the pptx/deck-building skill
#   physically cannot load. The CEO orchestrator must route, not build. Deep-merge —
#   no clobber of other agents.
#
# LAYER 3 — SYMLINK UNBLOCK
#   Adds the workspace real-path to skills.load.allowSymlinkTargets so the `tasks`
#   skill loads (symlink-escape guard was skipping it). Baked into the config write.
#
# LAYER 4 — SEED DEPARTMENT WORKSPACES
#   Ensures department rows are present in mission-control.db so department_slug
#   (e.g. "presentations") resolves to a real workspace_id instead of null/ceo-fallback.
#   Delegates to the existing 32-command-center-setup/scripts/seed-workspaces.py.
#
# Usage:
#   bash apply-routing-fix.sh              # apply all layers
#   bash apply-routing-fix.sh --dry-run    # print what WOULD change, no writes
#
# Idempotent: safe to re-run; every layer is guarded by a marker or state check.
# Backs up openclaw.json before any JSON edits.
#
# Exit codes:
#   0  — all layers applied (or already applied — idempotent no-op)
#   1  — fatal error (config missing, JSON invalid, etc.)

set -euo pipefail

DRY_RUN=0
for _arg in "$@"; do
  [[ "$_arg" == "--dry-run" ]] && DRY_RUN=1
done

# ─── Shared helpers ───────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONBOARDING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

_log() { printf '[apply-routing-fix] %s\n' "$*"; }
_warn() { printf '[apply-routing-fix] WARN: %s\n' "$*" >&2; }
_dry() { printf '[apply-routing-fix] DRY-RUN: %s\n' "$*"; }

# ─── Platform detection ───────────────────────────────────────────────────────

if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[apply-routing-fix] ERROR: cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw" >&2
  exit 1
fi

OC_CONFIG="$OC_ROOT/openclaw.json"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
OC_BACKUP="$OC_CONFIG.bak-routing-fix-$TIMESTAMP"

_log "config: $OC_CONFIG"
_log "dry-run: $DRY_RUN"

# ─── Backup ───────────────────────────────────────────────────────────────────

if [ "$DRY_RUN" = "0" ]; then
  cp "$OC_CONFIG" "$OC_BACKUP"
  _log "backed up to: $OC_BACKUP"
fi

# ─── Resolve main agent workspace (shared by L1 + L2 + L3) ──────────────────
# Priority:
#   1. agents.list[id=main].workspace (per-agent override)
#   2. agents.defaults.workspace via openclaw CLI
#   3. $OC_ROOT/workspace (canonical default)

WORKSPACE_DIR=""

# Step 1: per-agent workspace override on the "main" agent
WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 - <<'PYEOF'
import json, os, sys
try:
    cfg = json.load(open(os.environ['OC_JSON']))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws))
                sys.exit(0)
except Exception:
    pass
sys.exit(0)
PYEOF
) || WORKSPACE_DIR=""

# Step 2: agents.defaults.workspace via CLI
if [ -z "$WORKSPACE_DIR" ] && command -v openclaw >/dev/null 2>&1; then
  WORKSPACE_DIR=$(openclaw config get agents.defaults.workspace 2>/dev/null \
    | head -1 | python3 -c "
import sys, json, os
try:
    raw = sys.stdin.read().strip()
    print(os.path.expanduser(json.loads(raw) if raw.startswith('\"') else raw))
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi

# Step 3: canonical default
WORKSPACE_DIR="${WORKSPACE_DIR:-$OC_ROOT/workspace}"
[ ! -d "$WORKSPACE_DIR" ] && WORKSPACE_DIR="$OC_ROOT/workspace"

_log "resolved workspace: $WORKSPACE_DIR"

if [ "$DRY_RUN" = "0" ]; then
  mkdir -p "$WORKSPACE_DIR"
fi

AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
SOUL_FILE="$WORKSPACE_DIR/SOUL.md"

# ═════════════════════════════════════════════════════════════════════════════
# LAYER 1 — DOCTRINE INTO THE CORRECT AGENTS.MD + SOUL.MD
# ═════════════════════════════════════════════════════════════════════════════
_log "--- LAYER 1: doctrine injection ---"

ROLE_DISC_MARKER="<!-- ROLE_DISCIPLINE_V1 -->"
CEO_ROUTING_MARKER="<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
CEO_ORCH_V2_MARKER="<!-- CEO_ORCHESTRATOR_RULE_V2 -->"

# --- AGENTS.md: ROLE_DISCIPLINE_V1 ---
if grep -qF "$ROLE_DISC_MARKER" "$AGENTS_FILE" 2>/dev/null; then
  _log "L1: ROLE_DISCIPLINE_V1 already present in $AGENTS_FILE — no-op"
else
  if [ "$DRY_RUN" = "1" ]; then
    _dry "would inject ROLE_DISCIPLINE_V1 into $AGENTS_FILE"
  else
    touch "$AGENTS_FILE"
    ORIGINAL_CONTENT=$(cat "$AGENTS_FILE" 2>/dev/null || true)
    {
      cat <<'RDEOF'
<!-- ROLE_DISCIPLINE_V1 -->
## ROLE DISCIPLINE (non-negotiable — every agent, every level)

No agent decides what it will or will not do.

- The **CEO / master-orchestrator** is a ROUTER: it routes every task to a department by posting
  to `/api/tasks/ingest` with `department_slug`; it does not execute work, pick specialists,
  or commandeer sub-agents to keep control. Before doing any task itself it must seek and
  receive explicit owner permission — routing is always allowed without permission.
- A **department specialist** EXECUTES the task assigned to it against its SOP — including
  generating graphics/video via KIE.ai / Fal.ai — and does not refuse, redefine, or bounce
  its assigned role.
- An agent that overrides its defined role gets flagged. Persistent non-compliance (>20 flags)
  = the agent is reset (identity + soul deleted and rebuilt fresh).

This rule is role-scoped so it reinforces the CEO routing mandate WITHOUT gagging executing
specialists. Both behaviors — the CEO routing and specialists executing — are equally required.

---

RDEOF
      printf '%s' "$ORIGINAL_CONTENT"
    } > "$AGENTS_FILE"
    _log "L1: ROLE_DISCIPLINE_V1 injected at top of $AGENTS_FILE"
  fi
fi

# --- AGENTS.md: CEO_ROUTING_NO_LOOPHOLES_V1 ---
if grep -qF "$CEO_ROUTING_MARKER" "$AGENTS_FILE" 2>/dev/null; then
  _log "L1: CEO_ROUTING_NO_LOOPHOLES_V1 already present in $AGENTS_FILE — no-op"
else
  if [ "$DRY_RUN" = "1" ]; then
    _dry "would inject CEO_ROUTING_NO_LOOPHOLES_V1 into $AGENTS_FILE"
  else
    touch "$AGENTS_FILE"
    TMPF=$(mktemp)
    awk -v marker="$ROLE_DISC_MARKER" '
      BEGIN { injected=0; in_rd=0 }
      {
        print
        if (!injected && index($0, marker)) { in_rd=1 }
        if (in_rd && !injected && /^---[[:space:]]*$/) {
          print ""
          print "<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
          print "## CEO ROUTING — NO LOOPHOLES (closes all self-execution escape hatches)"
          print ""
          print "The CEO / master-orchestrator'\''s ONLY permitted routing action is:"
          print ""
          print "  **POST \`/api/tasks/ingest\` with \`department_slug: \"<slug>\"\`**"
          print ""
          print "This places the task on the department'\''s Kanban board. The DEPARTMENT assigns the specialist"
          print "and the persona. The doing belongs to the department — never to the CEO."
          print ""
          print "### Closed loopholes (ALL violations, no exceptions):"
          print ""
          print "| Loophole | Status |"
          print "|----------|--------|"
          print "| \"This task is trivial / simple / quick — I'\''ll just do it myself\" | VIOLATION |"
          print "| \"I know how to make this API call, I'\''ll handle it directly\" | VIOLATION |"
          print "| \"I'\''ll spawn a sub-agent and have it execute the work for me\" | VIOLATION — spawning a sub-agent to do production work IS the same as self-executing |"
          print "| \"I'\''m telling the sub-agent to call KIE.ai / Fal.ai for me\" | VIOLATION — same as above |"
          print "| \"I don'\''t know which department, so I'\''ll do it myself\" | VIOLATION — route to \`department_slug: \"general-task\"\` |"
          print "| \"The owner seemed to want a quick answer\" | VIOLATION — route and let the department respond |"
          print ""
          print "### What the CEO MAY do (exhaustive list):"
          print "- Have conversations with the owner"
          print "- POST to \`/api/tasks/ingest\` to route tasks"
          print "- Send Telegram messages"
          print "- Read workspace files"
          print "- Restart the gateway (orchestrator-only authority)"
          print "- Manage agent/department config"
          print ""
          print "### Owner-permission exception"
          print "Before the CEO would EVER do a task itself, it must FIRST seek AND RECEIVE explicit permission"
          print "and consent from the owner. Seeking permission alone is not enough — explicit consent must be"
          print "received. Without that explicit consent, the CEO routes — always."
          print ""
          print "---"
          print ""
          injected=1
        }
      }
    ' "$AGENTS_FILE" > "$TMPF"
    # If ROLE_DISCIPLINE marker was not found (older box), prepend at top
    if ! grep -qF "$CEO_ROUTING_MARKER" "$TMPF"; then
      ORIG2=$(cat "$AGENTS_FILE")
      {
        printf '<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->\n'
        printf '## CEO ROUTING — NO LOOPHOLES\n\n'
        printf 'The CEO'\''s ONLY permitted routing action: POST /api/tasks/ingest with department_slug.\n'
        printf 'No trivial-task, quick-API-call, or spawn-sub-agent exceptions.\n\n'
        printf '---\n\n'
        printf '%s' "$ORIG2"
      } > "$TMPF"
    fi
    mv "$TMPF" "$AGENTS_FILE"
    _log "L1: CEO_ROUTING_NO_LOOPHOLES_V1 injected into $AGENTS_FILE"
  fi
fi

# --- SOUL.md: PRIME DIRECTIVE ---
if grep -qF "$CEO_ORCH_V2_MARKER" "$SOUL_FILE" 2>/dev/null; then
  _log "L1: PRIME DIRECTIVE already present in $SOUL_FILE — no-op"
else
  if [ "$DRY_RUN" = "1" ]; then
    _dry "would inject PRIME DIRECTIVE (CEO_ORCHESTRATOR_RULE_V2) into $SOUL_FILE"
  else
    touch "$SOUL_FILE"
    SOUL_EXISTING=$(cat "$SOUL_FILE" 2>/dev/null || true)
    # Strip V1 block if present
    if echo "$SOUL_EXISTING" | grep -qF "<!-- CEO_ORCHESTRATOR_RULE_V1 -->"; then
      SOUL_EXISTING=$(echo "$SOUL_EXISTING" | python3 -c "
import sys, re
content = sys.stdin.read()
content = re.sub(r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '', content, count=1, flags=re.DOTALL)
print(content, end='')
")
    fi
    # Strip personal-assistant intro if present
    SOUL_EXISTING=$(echo "$SOUL_EXISTING" | python3 -c "
import sys, re
content = sys.stdin.read()
content = re.sub(r'^# SOUL\.md.*?^---\s*\n', '', content, count=1, flags=re.DOTALL | re.MULTILINE)
print(content.lstrip(), end='')
")
    {
      cat <<'PDEOF'
<!-- CEO_ORCHESTRATOR_RULE_V2 -->
## PRIME DIRECTIVE — I AM A TASK ROUTER. I ROUTE. THIS IS NOT OPTIONAL.

1. I am the master orchestrator (CEO). My one job is to ROUTE tasks. When any task or request
   reaches me, I ROUTE it to the correct DEPARTMENT — every time. I have NO permission to decide
   not to route, to refuse a task, or to choose what I will or will not do.
2. I do NOT do the work myself, and I do NOT pick the specialist or spawn/keep control of a
   sub-agent to do it. I route to the DEPARTMENT. The DEPARTMENT decides which specialist
   sub-agent and which persona are needed; the task gets a persona assigned; the task is placed
   on the Kanban board. The doing belongs to the department and its specialist — never to me.
3. Before I would EVER do a task myself, I must FIRST seek and RECEIVE explicit permission and
   consent from the owner (the human in control). Without that explicit consent, I route — always.
   (Routing is my default and is always allowed; I never need permission to route.)
4. If I cannot determine the right department, I route to the General Tasks department. I never
   self-execute because I am unsure, and I never hold a task to "stay in control" of it.
5. What I MAY do: have conversations, manage agents, manage departments, and route tasks.
   What I may NEVER do: refuse to route, decide who executes, execute the work myself, or
   commandeer a sub-agent to keep control.

### Routing = Creating a DEPARTMENT TASK (not spawning a sub-agent directly)

The correct routing action is POST to `/api/tasks/ingest` with `department_slug: "<slug>"`.
This places the task on the department Kanban — the DEPARTMENT assigns the specialist.

Spawning a sub-agent and instructing it to execute production work IS THE SAME VIOLATION as
executing the work yourself. If a sub-agent is spawned, it MUST read its own role files and
operate via the task board — it is not a production tool for the orchestrator.

### Binding Rules

- R1: Never generate images, videos, audio, or written deliverables
- R2: Never write to files, databases, or external APIs as a production action
- R3: Never use any skill that produces a deliverable (skills: [] enforced in config)
- R4: Every actionable request -> POST /api/tasks/ingest with department_slug
- R5: If CC unreachable -> escalate via Telegram, do NOT execute directly
- R6: If route is unclear -> use department_slug: "general-task", never self-execute
- R7: Permitted actions only: Telegram messaging, task-ingest POST, read workspace files, gateway restart

---

PDEOF
      printf '%s' "$SOUL_EXISTING"
    } > "$SOUL_FILE"
    _log "L1: PRIME DIRECTIVE written to $SOUL_FILE"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# LAYER 2 — STRUCTURAL PPTX DENY (skills:[] on main agent)
# ═════════════════════════════════════════════════════════════════════════════
_log "--- LAYER 2: structural pptx deny (skills:[] on main agent) ---"

L2_RESULT=$(python3 - "$OC_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())

agents_list = cfg.get("agents", {}).get("list", []) or []
main_agent = None
for ag in agents_list:
    if isinstance(ag, dict) and ag.get("id") == "main":
        main_agent = ag
        break

if main_agent is None:
    print("NO_MAIN_AGENT")
    sys.exit(0)

current_skills = main_agent.get("skills")
# Already set to empty list or explicit pptx deny?
if isinstance(current_skills, list) and len(current_skills) == 0:
    print("ALREADY_DENIED")
    sys.exit(0)

# Emit the pending change summary for dry-run display
print(f"WILL_SET: current skills={json.dumps(current_skills)} -> skills=[]")
PYEOF
) || L2_RESULT="ERROR"

if [ "$L2_RESULT" = "ALREADY_DENIED" ]; then
  _log "L2: skills:[] already set on main agent — no-op"
elif [ "$L2_RESULT" = "NO_MAIN_AGENT" ]; then
  _warn "L2: no agent with id=main found in openclaw.json agents.list — skipping"
elif [[ "$L2_RESULT" == "ERROR" || "$L2_RESULT" == *"Traceback"* ]]; then
  _warn "L2: could not inspect openclaw.json — skipping pptx deny layer"
else
  if [ "$DRY_RUN" = "1" ]; then
    _dry "L2: $L2_RESULT"
  else
    python3 - "$OC_CONFIG" <<'PYEOF'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())

agents_list = cfg.get("agents", {}).get("list", []) or []
for ag in agents_list:
    if isinstance(ag, dict) and ag.get("id") == "main":
        ag["skills"] = []
        break

cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
print("[apply-routing-fix] L2: skills:[] set on main agent")
PYEOF
    _log "L2: pptx deny (skills:[]) applied to main agent in openclaw.json"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# LAYER 3 — SYMLINK UNBLOCK (allowSymlinkTargets)
# ═════════════════════════════════════════════════════════════════════════════
_log "--- LAYER 3: symlink unblock (allowSymlinkTargets) ---"

# Resolve the real path of the workspace to add to allowSymlinkTargets
WS_REALPATH=""
if command -v realpath >/dev/null 2>&1; then
  WS_REALPATH=$(realpath -m "$WORKSPACE_DIR" 2>/dev/null) || WS_REALPATH="$WORKSPACE_DIR"
elif python3 -c "import pathlib" 2>/dev/null; then
  WS_REALPATH=$(python3 -c "import pathlib, os; print(str(pathlib.Path('$WORKSPACE_DIR').resolve()))" 2>/dev/null) || WS_REALPATH="$WORKSPACE_DIR"
else
  WS_REALPATH="$WORKSPACE_DIR"
fi

L3_RESULT=$(python3 - "$OC_CONFIG" "$WS_REALPATH" <<'PYEOF'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
ws_real = sys.argv[2]
cfg = json.loads(cfg_path.read_text())

current = cfg.get("skills", {}).get("load", {}).get("allowSymlinkTargets", []) or []
if isinstance(current, list) and ws_real in current:
    print("ALREADY_PRESENT")
else:
    print(f"WILL_ADD: {ws_real}")
PYEOF
) || L3_RESULT="ERROR"

if [ "$L3_RESULT" = "ALREADY_PRESENT" ]; then
  _log "L3: $WS_REALPATH already in allowSymlinkTargets — no-op"
elif [[ "$L3_RESULT" == "ERROR" || "$L3_RESULT" == *"Traceback"* ]]; then
  _warn "L3: could not inspect openclaw.json — skipping symlink unblock"
else
  if [ "$DRY_RUN" = "1" ]; then
    _dry "L3: $L3_RESULT"
  else
    python3 - "$OC_CONFIG" "$WS_REALPATH" <<'PYEOF'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
ws_real = sys.argv[2]
cfg = json.loads(cfg_path.read_text())

# Deep-merge: ensure skills.load.allowSymlinkTargets exists and contains ws_real
skills = cfg.setdefault("skills", {})
load = skills.setdefault("load", {})
targets = load.setdefault("allowSymlinkTargets", [])
if not isinstance(targets, list):
    targets = []
    load["allowSymlinkTargets"] = targets
if ws_real not in targets:
    targets.append(ws_real)

cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"[apply-routing-fix] L3: {ws_real} added to skills.load.allowSymlinkTargets")
PYEOF
    _log "L3: allowSymlinkTargets updated"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# LAYER 4 — SEED DEPARTMENT WORKSPACES
# ═════════════════════════════════════════════════════════════════════════════
_log "--- LAYER 4: seed department workspaces into mission-control.db ---"

SEED_SCRIPT=""
for _cand in \
  "$ONBOARDING_DIR/32-command-center-setup/scripts/seed-workspaces.py" \
  "$OC_ROOT/skills/32-command-center-setup/scripts/seed-workspaces.py" \
  "$HOME/.openclaw/skills/32-command-center-setup/scripts/seed-workspaces.py" \
  "/data/.openclaw/skills/32-command-center-setup/scripts/seed-workspaces.py"; do
  [ -f "$_cand" ] && SEED_SCRIPT="$_cand" && break
done

if [ -z "$SEED_SCRIPT" ]; then
  _warn "L4: seed-workspaces.py not found — skipping dept workspace seeding"
  _warn "L4: install Skill 32 first to enable dept seeding"
else
  _log "L4: found seed script: $SEED_SCRIPT"
  if [ "$DRY_RUN" = "1" ]; then
    _dry "L4: would run: python3 $SEED_SCRIPT"
  else
    # Detect DB first — if DB doesn't exist yet, seeding is deferred (CC not installed)
    DB_PATH=$(python3 - <<PYEOF
import sys
from pathlib import Path
import os
HOME = Path.home()

# Mirror seed-workspaces.py candidate list (PRD 1.3)
try:
    _SHARED_UTILS = Path("$ONBOARDING_DIR/shared-utils")
    sys.path.insert(0, str(_SHARED_UTILS))
    from resolve_db import find_dashboard_db
    p = find_dashboard_db()
    if p.exists():
        print(str(p))
        sys.exit(0)
except Exception:
    pass

candidates = [
    HOME / "projects/command-center/mission-control.db",
    HOME / "projects/mission-control/mission-control.db",
    Path("/data/projects/command-center/mission-control.db"),
    Path("/opt/mission-control/mission-control.db"),
    Path("/app/mission-control.db"),
]
for c in candidates:
    if c.exists():
        print(str(c))
        sys.exit(0)
sys.exit(1)
PYEOF
) || DB_PATH=""
    if [ -z "$DB_PATH" ]; then
      _warn "L4: mission-control.db not found — Command Center not installed yet; skipping seeding"
      _warn "L4: run apply-routing-fix.sh again after Skill 32 installs the dashboard"
    else
      _log "L4: mission-control.db found at: $DB_PATH"
      if python3 "$SEED_SCRIPT" 2>&1 | while IFS= read -r _ln; do _log "L4: $_ln"; done; then
        _log "L4: dept workspace seeding complete"
      else
        _warn "L4: seed-workspaces.py exited non-zero — check output above"
      fi
    fi
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# Validate config after JSON edits
# ═════════════════════════════════════════════════════════════════════════════
if [ "$DRY_RUN" = "0" ] && command -v openclaw >/dev/null 2>&1; then
  _log "running: openclaw config validate"
  if ! openclaw config validate 2>&1 | while IFS= read -r _vl; do _log "validate: $_vl"; done; then
    _log "ERROR: openclaw config validate failed — rolling back to backup"
    cp "$OC_BACKUP" "$OC_CONFIG"
    echo "[apply-routing-fix] FATAL: config validation failed; rolled back to $OC_BACKUP" >&2
    exit 1
  fi
  _log "config validate: PASSED"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Summary
# ═════════════════════════════════════════════════════════════════════════════
echo ""
_log "DONE"
_log "  Backup:     ${OC_BACKUP:-n/a (dry-run)}"
_log "  Config:     $OC_CONFIG"
_log "  AGENTS.md:  $AGENTS_FILE"
_log "  SOUL.md:    $SOUL_FILE"
_log "  Workspace:  $WORKSPACE_DIR"
if [ "$DRY_RUN" = "1" ]; then
  _log "(dry-run — no files were written)"
fi
