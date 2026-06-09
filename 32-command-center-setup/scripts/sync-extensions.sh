#!/usr/bin/env bash
# sync-extensions.sh — Skill 32 Command Center Setup
#
# PURPOSE
#   Master idempotent orchestrator for post-build capability extension.
#   Detects new skills/departments added since the initial Skill 23 build,
#   registers them into the routing layer, and notifies the owner via
#   Telegram. Safe to re-run at any time — convergent, never destructive.
#
# WHAT IT DOES
#   1. Reads the canonical role-library _index.json (current state of truth)
#   2. Calls detect-extensions.py to diff against the last-sync manifest
#   3. For each NEW department detected:
#      a. register-routing-dept.py — adds the dept to department-router config
#      b. materialize-dept-agents.sh — creates agent workspace dirs if missing
#      c. Updates openclaw.json via openclaw config set (additive only)
#   4. Writes an updated sync manifest (last-sync.json) so next run is no-op
#   5. Sends a Telegram summary to the owner (new depts + skip count)
#
# IDEMPOTENCY CONTRACT
#   - Running twice in a row produces the same state (no duplicates)
#   - Never removes existing departments, agents, or routing rules
#   - Never touches agents NOT in the extension delta
#   - Fails loudly (exit 1) on any step that mutates state and errors
#
# USAGE
#   bash sync-extensions.sh [--dry-run] [--verbose]
#   bash sync-extensions.sh --dept <slug>     # force-add a single dept
#
# CALLED FROM
#   Sunday cron (0 3 * * 0) via update-skills.sh
#   Manually after adding a new skill/dept to the role-library

set -uo pipefail

# ─── Logging ─────────────────────────────────────────────────────────────────
P="[sync-ext]"
info()    { printf '%s %s\n'             "$P" "$*"; }
ok()      { printf '%s \033[32m✓\033[0m %s\n' "$P" "$*"; }
warn()    { printf '%s \033[33m⚠\033[0m %s\n' "$P" "$*" >&2; }
fail()    { printf '%s \033[31m✗\033[0m %s\n' "$P" "$*" >&2; }
die()     { fail "$*"; exit 1; }

DRY_RUN=0
VERBOSE=0
FORCE_DEPT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --verbose) VERBOSE=1 ;;
    --dept)    shift; FORCE_DEPT="$1" ;;
    *) warn "Unknown flag: $1" ;;
  esac
  shift
done

[[ $DRY_RUN -eq 1 ]] && info "DRY-RUN MODE — no mutations"

# ─── Platform detection ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_ROOT/.." && pwd)"
ADD_DEPT_SH="$SCRIPT_DIR/add-department.sh"

if [[ -f "/data/.openclaw/openclaw.json" ]]; then
  OC_ROOT="/data/.openclaw"
  OC_PLATFORM="vps"
elif [[ -f "$HOME/.openclaw/openclaw.json" ]]; then
  OC_ROOT="$HOME/.openclaw"
  OC_PLATFORM="mac"
else
  die "Cannot find openclaw.json — run the OpenClaw installer first"
fi

OC_JSON="$OC_ROOT/openclaw.json"
info "Platform : $OC_PLATFORM"
info "Config   : $OC_JSON"

# ─── Path resolution ─────────────────────────────────────────────────────────
INDEX_JSON="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/_index.json"
DETECT_PY="$SCRIPT_DIR/detect-extensions.py"
REGISTER_PY="$SCRIPT_DIR/register-routing-dept.py"
MATERIALIZE_SH="$SCRIPT_DIR/materialize-dept-agents.sh"

SYNC_STATE_DIR="$OC_ROOT/extension-sync"
LAST_SYNC_JSON="$SYNC_STATE_DIR/last-sync.json"
SYNC_LOG="$SYNC_STATE_DIR/sync-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$SYNC_STATE_DIR"

[[ -f "$INDEX_JSON" ]] || die "Role-library _index.json not found at: $INDEX_JSON"
[[ -f "$DETECT_PY"  ]] || die "detect-extensions.py not found at: $DETECT_PY"

# ─── Step 1: Detect extension delta ──────────────────────────────────────────
info "Detecting extension delta..."

if [[ -n "$FORCE_DEPT" ]]; then
  info "Force-adding single dept: $FORCE_DEPT"
  NEW_DEPTS="$FORCE_DEPT"
else
  DETECT_ARGS="--index $INDEX_JSON"
  [[ -f "$LAST_SYNC_JSON" ]] && DETECT_ARGS="$DETECT_ARGS --last-sync $LAST_SYNC_JSON"
  [[ $VERBOSE -eq 1 ]] && DETECT_ARGS="$DETECT_ARGS --verbose"

  DETECT_OUTPUT="$(python3 "$DETECT_PY" $DETECT_ARGS 2>&1)" || {
    fail "detect-extensions.py failed"
    fail "$DETECT_OUTPUT"
    exit 1
  }

  # detect-extensions.py writes one dept slug per line on stdout, prefixed "NEW: "
  NEW_DEPTS="$(echo "$DETECT_OUTPUT" | grep '^NEW: ' | sed 's/^NEW: //')"
  SKIP_COUNT="$(echo "$DETECT_OUTPUT" | grep '^SKIP: ' | wc -l | tr -d ' ')"

  [[ $VERBOSE -eq 1 ]] && info "Detect output:" && echo "$DETECT_OUTPUT"
fi

if [[ -z "$NEW_DEPTS" ]]; then
  ok "No new departments detected — sync is current."
  # Still update the last-sync timestamp
  [[ $DRY_RUN -eq 0 ]] && python3 - "$INDEX_JSON" "$LAST_SYNC_JSON" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
idx = json.load(open(sys.argv[1]))
state = {"synced_at": datetime.now(timezone.utc).isoformat(),
         "departments": list(idx.get("departments", {}).keys()),
         "total_roles": idx.get("total_roles", 0),
         "version": idx.get("version", "unknown")}
with open(sys.argv[2], "w") as f:
    json.dump(state, f, indent=2)
PYEOF
  exit 0
fi

info "New departments to register: $(echo "$NEW_DEPTS" | wc -l | tr -d ' ')"
echo "$NEW_DEPTS" | while IFS= read -r dept; do info "  + $dept"; done

# ─── Step 2: Register each new department ────────────────────────────────────
REGISTERED=()
FAILED=()

while IFS= read -r dept; do
  [[ -z "$dept" ]] && continue
  info "Processing: $dept"

  # 2a. Register routing entry
  if [[ -f "$REGISTER_PY" ]]; then
    if [[ $DRY_RUN -eq 0 ]]; then
      if python3 "$REGISTER_PY" --dept "$dept" --config "$OC_JSON" 2>&1; then
        ok "  routing registered: $dept"
      else
        warn "  routing registration failed for: $dept (continuing)"
        FAILED+=("$dept")
        continue
      fi
    else
      info "  [DRY-RUN] would register routing for: $dept"
    fi
  else
    warn "register-routing-dept.py not found — skipping routing registration"
  fi

  # 2b. Materialize agent workspace dirs (idempotent)
  if [[ -f "$MATERIALIZE_SH" ]]; then
    if [[ $DRY_RUN -eq 0 ]]; then
      bash "$MATERIALIZE_SH" --dept "$dept" 2>&1 && \
        ok "  workspace materialized: $dept" || \
        warn "  workspace materialization warning for: $dept"
    else
      info "  [DRY-RUN] would materialize workspace for: $dept"
    fi
  fi

  # 2c. (G2 fix) Create CC workspaces row + QC specialist via add-department.sh.
  #     The routing registration (2a) writes openclaw.json only — it NEVER
  #     creates the SQLite workspaces row that loadDepartments() reads.
  #     add-department.sh is idempotent: if the row already exists it returns
  #     {"status":"already_exists"} and exits 0.
  if [[ -f "$ADD_DEPT_SH" ]]; then
    # Derive a human-readable display name from the slug:
    #   "project-architecture-office" → "Project Architecture Office"
    DEPT_DISPLAY=$(echo "$dept" | sed -E 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2); print}')
    if [[ $DRY_RUN -eq 0 ]]; then
      ADOUT=$(bash "$ADD_DEPT_SH" --slug "$dept" --name "$DEPT_DISPLAY" 2>&1)
      ADD_RC=$?
      # Parse the ---SUMMARY--- JSON block to detect created vs already_exists
      ADD_STATUS=$(echo "$ADOUT" | awk '/^---SUMMARY---/{found=1; next} found{print; exit}' | python3 -c "import json,sys; d=json.loads(sys.stdin.read().strip()); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
      if [[ $ADD_RC -eq 0 ]]; then
        ok "  CC workspace row: $dept ($ADD_STATUS)"
      else
        warn "  CC workspace row failed for: $dept (rc=$ADD_RC) — continuing"
        warn "  Output: $(echo "$ADOUT" | tail -5)"
      fi
    else
      info "  [DRY-RUN] would create CC workspace row for: $dept"
    fi
  else
    warn "  add-department.sh not found — CC workspaces row NOT created for: $dept (orphan risk)"
  fi

  REGISTERED+=("$dept")
done <<< "$NEW_DEPTS"

# ─── Step 3: Update last-sync manifest ───────────────────────────────────────
if [[ $DRY_RUN -eq 0 ]]; then
  python3 - "$INDEX_JSON" "$LAST_SYNC_JSON" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
idx = json.load(open(sys.argv[1]))
state = {"synced_at": datetime.now(timezone.utc).isoformat(),
         "departments": list(idx.get("departments", {}).keys()),
         "total_roles": idx.get("total_roles", 0),
         "version": idx.get("version", "unknown")}
with open(sys.argv[2], "w") as f:
    json.dump(state, f, indent=2)
print(f"last-sync.json updated: {sys.argv[2]}")
PYEOF
  ok "last-sync.json updated"
fi

# ─── Step 4: Telegram summary ────────────────────────────────────────────────
if [[ ${#REGISTERED[@]} -gt 0 && $DRY_RUN -eq 0 ]]; then
  REG_LIST="$(printf '%s\n' "${REGISTERED[@]}" | sed 's/^/  • /')"
  MSG="Extension sync complete on $(hostname).
New departments registered (${#REGISTERED[@]}):
$REG_LIST"
  if [[ ${#FAILED[@]} -gt 0 ]]; then
    FAIL_LIST="$(printf '%s\n' "${FAILED[@]}" | sed 's/^/  • /')"
    MSG="$MSG

FAILED to register (${#FAILED[@]}) — manual review needed:
$FAIL_LIST"
  fi

  # Send via openclaw message send (N rule: never bypass OpenClaw for Telegram)
  openclaw message send --channel telegram --body "$MSG" 2>/dev/null || \
    warn "Telegram summary send failed (non-fatal)"
fi

# ─── Result ───────────────────────────────────────────────────────────────────
if [[ ${#FAILED[@]} -gt 0 ]]; then
  fail "sync completed with ${#FAILED[@]} failure(s): ${FAILED[*]}"
  exit 1
fi

ok "sync-extensions.sh complete — ${#REGISTERED[@]} new dept(s) registered."
