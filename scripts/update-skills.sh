#!/bin/bash
# BlackCEO System - Safe Update Script v11.18.0
# Surgical Update System - Download, compare, backup, apply, notify
#
# Improvements over previous version:
# - Dependency check (python3, curl, unzip)
# - .onboarding-version file creation
# - Better error handling with rollback
# - Verification after applying updates
# - Model deprecation check
# - Dry-run mode
# - Better logging

set -euo pipefail

# ── CONFIGURATION ──
REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
REPO_FOLDER="openclaw-onboarding-main"
BACKUP_BASE="$HOME/Downloads/openclaw-backups"
DRY_RUN="${1:-}"

# ── DEPENDENCY CHECK ──
check_dependencies() {
  local MISSING=()
  command -v python3 &>/dev/null || MISSING+=("python3")
  command -v curl &>/dev/null || MISSING+=("curl")
  command -v unzip &>/dev/null || MISSING+=("unzip")
  if [ ${#MISSING[@]} -gt 0 ]; then
    echo "ERROR: Missing required tools: ${MISSING[*]}"
    echo "Install them and try again."
    exit 1
  fi
}
check_dependencies

# ── U008: PRE-FLIGHT SPEND/BUDGET CHECK ────────────────────────────────────
# Checks remaining org budget before paid-API steps (persona embedding, QC
# gates). Controlled by OPENCLAW_ORG_SPEND_LIMIT (USD cents). Default (unset):
# no-op. GATE mode when OPENCLAW_ORG_SPEND_GATE=1, otherwise WARN only.
# -----------------------------------------------------------------------------
_spend_budget_ok=1
if [ -n "${OPENCLAW_ORG_SPEND_LIMIT:-}" ]; then
  _spend_remaining=""
  _spend_source=""
  # 1) openclaw CLI
  if command -v openclaw >/dev/null 2>&1; then
    _spend_remaining="$(openclaw org spend 2>/dev/null || true)"
    [ -n "$_spend_remaining" ] && { _spend_remaining="$(printf '%s' "$_spend_remaining" | tr -dc '0-9')"; _spend_source="openclaw org spend"; }
  fi
  # 2) budget tracking file
  [ -z "$_spend_remaining" ] && [ -f "/data/.openclaw/.org-budget-remaining" ] && { _spend_remaining="$(cat /data/.openclaw/.org-budget-remaining 2>/dev/null | tr -d '[:space:]' | tr -dc '0-9' || true)"; _spend_source="/data/.openclaw/.org-budget-remaining"; }
  [ -z "$_spend_remaining" ] && [ -f "$HOME/.openclaw/.org-budget-remaining" ] && { _spend_remaining="$(cat "$HOME/.openclaw/.org-budget-remaining" 2>/dev/null | tr -d '[:space:]' | tr -dc '0-9' || true)"; _spend_source="$HOME/.openclaw/.org-budget-remaining"; }
  if [ -n "$_spend_remaining" ] && [ "$_spend_remaining" -lt "$OPENCLAW_ORG_SPEND_LIMIT" ] 2>/dev/null; then
    echo "  * PRE-FLIGHT SPEND GATE: remaining budget ($_spend_remaining) < threshold ($OPENCLAW_ORG_SPEND_LIMIT, source: $_spend_source)" >&3
    if [ "${OPENCLAW_ORG_SPEND_GATE:-0}" = "1" ]; then
      echo "FATAL: OPENCLAW_ORG_SPEND_GATE=1 and spend budget below threshold -- refusing to proceed." >&3
      exit 1
    fi
  else
    [ -n "$_spend_remaining" ] && echo "  [spend-check] OK: remaining budget ($_spend_remaining) >= threshold ($OPENCLAW_ORG_SPEND_LIMIT)" >&3
  fi
fi

# ── LOG FILE ──
LOG_FILE="$HOME/.openclaw/skills/.update-log"
mkdir -p "$(dirname "$LOG_FILE")"
exec 3>&1 4>&2
trap 'exec 1>&3 2>&4' EXIT
exec 1>>"$LOG_FILE" 2>&1

# ── UI HELPERS ──
step_counter=0
show_step() {
  step_counter=$((step_counter + 1))
  echo "[$step_counter/7] $1" >&3
}
show_success() { echo "  ✓ $1" >&3; }
show_info() { echo "  ℹ $1" >&3; }
show_error() { echo "  ✗ $1" >&3; }

# ── TIMESTAMP ──
log_ts() { date '+%Y-%m-%d %H:%M:%S'; }

# ── DISCOVER SKILLS DIRECTORY ──
# Active-dir-first: prefer the directory the running agent actually loads.
#   VPS  (/data exists) → /data/.openclaw/skills
#   Mac               → ~/.openclaw/skills
# Falls back to ~/Downloads/openclaw-master-files only when the active
# dir is absent.  Updating the Downloads copy while the active dir is
# untouched is a silent no-op and must never be reported as success.
discover_skills_dir() {
  if [ -d /data ]; then
    ACTIVE_DIR="/data/.openclaw/skills"
  else
    ACTIVE_DIR="$HOME/.openclaw/skills"
  fi

  if [ -d "$ACTIVE_DIR" ]; then
    SKILL_COUNT=$(ls -d "$ACTIVE_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$ACTIVE_DIR"
      return
    fi
    # Exists but empty — still prefer it for fresh installs
    echo "$ACTIVE_DIR"
    return
  fi

  # Legacy fallback: Downloads copy
  LEGACY_DIR="$HOME/Downloads/openclaw-master-files"
  if [ -d "$LEGACY_DIR" ]; then
    SKILL_COUNT=$(ls -d "$LEGACY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$LEGACY_DIR"
      return
    fi
  fi

  echo "$ACTIVE_DIR"
}

SKILLS_DIR=$(discover_skills_dir)
STAGE_DIR="/tmp/blackceo-update-$$"
STAGE_ZIP="/tmp/blackceo-update-$$.zip"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"
WORKSPACE_ROOT="$HOME/clawd"
[ ! -d "$WORKSPACE_ROOT" ] && WORKSPACE_ROOT="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_ROOT/AGENTS.md"

echo "" >&3
echo "============================================" >&3
echo " BlackCEO System - Update Check" >&3
echo "============================================" >&3
echo "" >&3
echo "[$(log_ts)] Update check started" >> "$LOG_FILE"

# ── STEP 1: Current version ──
show_step "Checking current version..."
mkdir -p "$SKILLS_DIR"
LOCAL_VER="none"
if [ -f "$SKILLS_DIR/.onboarding-version" ]; then
  LOCAL_VER=$(cat "$SKILLS_DIR/.onboarding-version" | tr -d '[:space:]')
fi
show_info "Installed: $LOCAL_VER"

# ── STEP 2: Download latest ──
show_step "Downloading latest from GitHub..."
rm -rf "$STAGE_DIR" "$STAGE_ZIP"
if ! curl -fsSL "$REPO_URL" -o "$STAGE_ZIP" 2>/dev/null; then
  show_error "Download failed. Check internet connection."
  echo "[$(log_ts)] ERROR: Download failed" >> "$LOG_FILE"
  exit 1
fi
if ! unzip -qo "$STAGE_ZIP" -d "$STAGE_DIR" 2>/dev/null; then
  show_error "Failed to extract archive."
  echo "[$(log_ts)] ERROR: Extraction failed" >> "$LOG_FILE"
  rm -rf "$STAGE_DIR" "$STAGE_ZIP"
  exit 1
fi
REPO_DIR="$STAGE_DIR/$REPO_FOLDER"
if [ ! -d "$REPO_DIR" ]; then
  show_error "Unexpected archive structure."
  echo "[$(log_ts)] ERROR: Archive structure unexpected" >> "$LOG_FILE"
  rm -rf "$STAGE_DIR" "$STAGE_ZIP"
  exit 1
fi

REMOTE_VER="unknown"
if [ -f "$REPO_DIR/version" ]; then
  REMOTE_VER=$(cat "$REPO_DIR/version" | tr -d '[:space:]')
fi
show_info "Latest: $REMOTE_VER"

# ── STEP 3: Compare versions ──
show_step "Comparing versions..."
if [ "$LOCAL_VER" = "$REMOTE_VER" ]; then
  echo "" >&3
  show_success "Already up to date ($LOCAL_VER). Nothing to do."
  echo "[$(log_ts)] No update needed ($LOCAL_VER)" >> "$LOG_FILE"
  rm -rf "$STAGE_DIR" "$STAGE_ZIP"
  exit 0
fi

echo "" >&3
echo "Update available: $LOCAL_VER -> $REMOTE_VER" >&3
echo ""

# ── STEP 4: Check deprecated models ──
show_step "Checking deprecated models..."
DEPRECATED_FILE="$REPO_DIR/scripts/deprecated-models.json"
if [ -f "$DEPRECATED_FILE" ]; then
  DEP_COUNT=$(python3 -c "import json; d=json.load(open('$DEPRECATED_FILE')); print(len(d.get('deprecated',[])))" 2>/dev/null || echo "0")
  if [ "$DEP_COUNT" -gt "0" ]; then
    show_info "$DEP_COUNT deprecated models detected"
    python3 -c "
import json
d = json.load(open('$DEPRECATED_FILE'))
for m in d.get('deprecated', []):
    print(f'  ⚠ {m[\"model\"]} -> {m.get(\"replacement\", \"no replacement\")} (removal: {m[\"removalDate\"]})')
" 2>/dev/null >&3
  fi
else
  show_info "No deprecated-models.json found"
fi

# ── STEP 5: Per-skill comparison ──
show_step "Analyzing skill changes..."


# ────────────────────────────────────────────────────────────────────────────
# CONTENT COMPARISON — the sync signal. Version strings are NOT.
#
# WHY: canonical routinely edits a skill tree's contents WITHOUT bumping that
# tree's skill-version.txt (23 of 62 versioned trees were in that state at
# origin/main 2d7bb304). A sync that decides on version-string equality
# therefore reports "unchanged" for trees whose bytes differ, and shared-utils/
# and universal-sops/ carry no version file at all, so a version gate has
# nothing to evaluate for them. Decisions below are made on CONTENT.
#
# DIRECTIONAL ON PURPOSE: `_OC_TREE_MISSING` = a SOURCE file that is absent on
# the box (or an entire absent tree). `_OC_TREE_DIFFERS` = a source file present
# on the box with different bytes. Destination-only extras (__pycache__, *.bak,
# runtime logs, per-box resolved artifacts) are NOT drift and must never force a
# re-copy or fail a gate — the copy semantics are an additive merge, so
# "source ⊆ dest, byte-for-byte" is the correct and complete health assertion.
#
# FAIL-CLOSED: if `diff` is unavailable we report drift, so the caller re-syncs
# rather than silently skipping.
#
# NOTE: the `case` patterns below interpolate directory paths. Glob metacharacters
# in a skills-dir path would widen the match; all real paths are $HOME/... or
# /tmp/... so this is safe in practice, and a widened match can only cause an
# extra (harmless) re-sync, never a skipped one.
# ────────────────────────────────────────────────────────────────────────────
_OC_TREE_MISSING=""
_OC_TREE_DIFFERS=""
_ocs_tree_compare() {
  local _src="${1%/}" _dst="${2%/}" _out _line
  _OC_TREE_MISSING=""
  _OC_TREE_DIFFERS=""
  [ -d "$_src" ] || return 0
  if ! command -v diff >/dev/null 2>&1; then
    _OC_TREE_MISSING=" (diff unavailable — assuming drift)"
    return 0
  fi
  if [ ! -d "$_dst" ]; then
    _OC_TREE_MISSING=" (entire tree absent: $_dst)"
    return 0
  fi
  _out="$(diff -rq \
            -x '.git' -x '__pycache__' -x '*.pyc' -x '*.pyo' -x '.DS_Store' \
            -x '*.bak' -x '*.bak-*' -x '.wired-*' \
            "$_src" "$_dst" 2>/dev/null || true)"
  [ -n "$_out" ] || return 0
  while IFS= read -r _line; do
    case "$_line" in
      "Only in $_src"*)   _OC_TREE_MISSING="${_OC_TREE_MISSING} ${_line#Only in }" ;;
      "Files "*" differ") _OC_TREE_DIFFERS="${_OC_TREE_DIFFERS} ${_line}" ;;
    esac
  done < <(printf '%s\n' "$_out")
  return 0
}

# _ocs_tree_in_sync <src> <dst>
#   rc 0 = every source file is present on the box with identical bytes
#   rc 1 = at least one source file is absent OR differs
_ocs_tree_in_sync() {
  _ocs_tree_compare "$1" "$2"
  [ -z "$_OC_TREE_MISSING" ] && [ -z "$_OC_TREE_DIFFERS" ]
}

SKILL_NAMES=()
SKILL_ACTIONS=()
SKOLD_VERSIONS=()
SKNEW_VERSIONS=()

NEW_COUNT=0
UPDATE_COUNT=0
SKIP_COUNT=0
DRIFT_COUNT=0

for SKILL_PATH in "$REPO_DIR"/[0-9]*/; do
  [ -d "$SKILL_PATH" ] || continue
  SNAME=$(basename "$SKILL_PATH")
  case "$SNAME" in *ARCHIVED*) continue ;; esac

  STAGED_V="unknown"
  LOCAL_V="none"
  [ -f "$SKILL_PATH/skill-version.txt" ] && STAGED_V=$(cat "$SKILL_PATH/skill-version.txt" | tr -d '[:space:]' | cut -d'#' -f1)
  [ -f "$SKILLS_DIR/$SNAME/skill-version.txt" ] && LOCAL_V=$(cat "$SKILLS_DIR/$SNAME/skill-version.txt" | tr -d '[:space:]' | cut -d'#' -f1)

  SKILL_NAMES+=("$SNAME")
  SKOLD_VERSIONS+=("$LOCAL_V")
  SKNEW_VERSIONS+=("$STAGED_V")

  if [ -d "$SKILLS_DIR/$SNAME" ]; then
    if [ "$LOCAL_V" = "none" ] || [ "$LOCAL_V" != "$STAGED_V" ]; then
      SKILL_ACTIONS+=("UPDATE")
      UPDATE_COUNT=$((UPDATE_COUNT + 1))
    elif _ocs_tree_in_sync "${SKILL_PATH%/}" "$SKILLS_DIR/$SNAME"; then
      SKILL_ACTIONS+=("SKIP")
      SKIP_COUNT=$((SKIP_COUNT + 1))
    else
      # SAME version string, DIFFERENT bytes. This is the exact case that
      # silently under-synced the fleet: the old gate was `[ "$LOCAL_V" =
      # "$STAGED_V" ] -> SKIP`, so a tree whose contents changed without a
      # version bump — or whose files were never delivered at all — was
      # reported as "unchanged" forever. Content wins over the version string.
      SKILL_ACTIONS+=("UPDATE")
      UPDATE_COUNT=$((UPDATE_COUNT + 1))
      DRIFT_COUNT=$((DRIFT_COUNT + 1))
      echo "  ! $SNAME: version $LOCAL_V unchanged but CONTENT drifted -> forcing update" >&3
    fi
  else
    SKILL_ACTIONS+=("NEW")
    NEW_COUNT=$((NEW_COUNT + 1))
  fi
done

echo "  Summary: $NEW_COUNT new, $UPDATE_COUNT updates, $SKIP_COUNT unchanged ($DRIFT_COUNT of the updates are CONTENT drift at an unchanged version string)" >&3

# ── STEP 6: Back up config ──
show_step "Creating backup..."
mkdir -p "$BACKUP_BASE"
if [ -f "$OPENCLAW_CONFIG" ]; then
  BACKUP_NAME="openclaw-json-backup-$(date +%Y-%m-%d-%H%M).json"
  cp "$OPENCLAW_CONFIG" "$BACKUP_BASE/$BACKUP_NAME"
  show_success "Config backed up to $BACKUP_BASE/$BACKUP_NAME"
fi

# ── STEP 7: Dry run check ──
if [ "$DRY_RUN" = "--dry-run" ]; then
  echo "" >&3
  show_info "DRY RUN - No changes applied"
  show_info "Would update: $LOCAL_VER -> $REMOTE_VER"
  show_info "New: $NEW_COUNT, Updated: $UPDATE_COUNT, Skipped: $SKIP_COUNT"
  rm -rf "$STAGE_DIR" "$STAGE_ZIP"
  exit 0
fi

# ── STEP 8: Apply updates ──
show_step "Applying updates..."

PROTECTED="AGENTS.md MEMORY.md SOUL.md USER.md IDENTITY.md HEARTBEAT.md TOOLS.md"
idx=0
APPLIED_COUNT=0
HAS_WIRE_MIGRATIONS=0

for SNAME in "${SKILL_NAMES[@]}"; do
  ACTION="${SKILL_ACTIONS[$idx]}"
  if [ "$ACTION" = "SKIP" ]; then
    idx=$((idx + 1))
    continue
  fi

  STAGED_PATH="$REPO_DIR/$SNAME"
  LOCAL_PATH="$SKILLS_DIR/$SNAME"
  [ -d "$STAGED_PATH" ] || { idx=$((idx + 1)); continue; }
  mkdir -p "$LOCAL_PATH"

  # ── A.2 v2: detect wire migration skills ────────────────────────────────
  # Trigger: skill has a wire.sh (general) OR is one of the known wire skills
  # (35/36/38).  Skill 44 is NOT included: it ships NO wire.sh and writes NO
  # convertandflow-migration marker, so a 44-only run must NOT fire the gate.
  SKILL_NUM="${SNAME%%-*}"
  if echo "$SKILL_NUM" | grep -qE '^(35|36|38)$' || [ -f "$STAGED_PATH/wire.sh" ]; then
    HAS_WIRE_MIGRATIONS=1
  fi

  for ITEM in "$STAGED_PATH"/*; do
    FNAME=$(basename "$ITEM")
    IS_PROT=false
    for P in $PROTECTED; do
      [ "$FNAME" = "$P" ] && IS_PROT=true && break
    done
    if [ "$IS_PROT" = true ] && [ -f "$LOCAL_PATH/$FNAME" ]; then
      continue
    fi
    if [ -d "$ITEM" ]; then
      cp -r "$ITEM" "$LOCAL_PATH/"
    else
      cp "$ITEM" "$LOCAL_PATH/"
    fi
  done

  APPLIED_COUNT=$((APPLIED_COUNT + 1))
  echo "  ✓ $SNAME ($ACTION)" >&3
  idx=$((idx + 1))
done

# ── Migration to canonical path removed ──
# Previously this block forced SKILLS_DIR back to ~/Downloads/openclaw-master-files
# even when the active dir was ~/.openclaw/skills (Mac) or /data/.openclaw/skills
# (VPS), causing the Downloads copy to be updated while the running agent's active
# dir was silently left on old versions.  discover_skills_dir() now correctly
# targets the active dir from the start; no post-apply migration needed.

# ── Copy root files and scripts ──
for RF in "Start Here.md" README.md CHANGELOG.md version; do
  [ -f "$REPO_DIR/$RF" ] && cp "$REPO_DIR/$RF" "$SKILLS_DIR/../" 2>/dev/null || true
done
[ -d "$REPO_DIR/scripts" ] && cp -r "$REPO_DIR/scripts" "$SKILLS_DIR/../" 2>/dev/null || true

# ── Copy deprecated-models.json ──
if [ -f "$REPO_DIR/scripts/deprecated-models.json" ]; then
  cp "$REPO_DIR/scripts/deprecated-models.json" "$SKILLS_DIR/../scripts/" 2>/dev/null || true
fi

# ── Refresh the two UNVERSIONED shared libraries ──────────────────────────
# shared-utils/ (the persona engine: persona_for_job.py, embedding_engine.py,
# the drift/grounding probes, ledger_reconciler_core.py, ...) and
# universal-sops/ (the Skill 47/48 SOP cluster) carry NO skill-version.txt, so
# the version-gated loop above had nothing to evaluate for them and this script
# referenced neither tree ANYWHERE — `grep -c shared-utils` returned 0. Every
# box whose weekly cron runs this script could therefore never receive them at
# any version, forever. Mirrors update-skills.sh (repo root) 1503-1535.
SHARED_TREE_FAIL=""
if [ -d "$REPO_DIR/shared-utils" ]; then
  mkdir -p "$SKILLS_DIR/shared-utils"
  # Trailing /. = additive merge: CREATES files absent on the box and
  # overwrites drifted ones, without deleting box-local extras.
  if ! cp -r "$REPO_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"; then
    SHARED_TREE_FAIL="${SHARED_TREE_FAIL} shared-utils(cp-failed)"
  fi
  chmod +x "$SKILLS_DIR/shared-utils/"*.sh "$SKILLS_DIR/shared-utils/"*.py 2>/dev/null || true
  _ocs_tree_compare "$REPO_DIR/shared-utils" "$SKILLS_DIR/shared-utils"
  if [ -n "$_OC_TREE_MISSING" ]; then
    SHARED_TREE_FAIL="${SHARED_TREE_FAIL} shared-utils(absent:${_OC_TREE_MISSING})"
  else
    show_success "shared-utils refreshed ($SKILLS_DIR/shared-utils)"
  fi
  # Post-copy byte differences are surfaced but do NOT withhold the stamp:
  # anything that legitimately rewrites a shared-utils file at install time
  # would otherwise block the stamp fleet-wide. Absence still gates.
  [ -n "$_OC_TREE_DIFFERS" ] && show_info "shared-utils: post-copy content differences:${_OC_TREE_DIFFERS}" || true
fi
if [ -d "$REPO_DIR/universal-sops" ]; then
  # Destructive replace (matches the root updater) so canonical deletions
  # propagate. Because the tree is wiped first, a partial cp leaves the box
  # with FEWER SOPs than it started with — hence the gate below.
  rm -rf "$SKILLS_DIR/universal-sops"
  if ! cp -r "$REPO_DIR/universal-sops" "$SKILLS_DIR/"; then
    SHARED_TREE_FAIL="${SHARED_TREE_FAIL} universal-sops(cp-failed)"
  fi
  _ocs_tree_compare "$REPO_DIR/universal-sops" "$SKILLS_DIR/universal-sops"
  if [ -n "$_OC_TREE_MISSING" ]; then
    SHARED_TREE_FAIL="${SHARED_TREE_FAIL} universal-sops(absent:${_OC_TREE_MISSING})"
  else
    show_success "universal-sops refreshed ($SKILLS_DIR/universal-sops)"
  fi
  [ -n "$_OC_TREE_DIFFERS" ] && show_info "universal-sops: post-copy content differences:${_OC_TREE_DIFFERS}" || true
fi
if [ -n "$SHARED_TREE_FAIL" ]; then
  show_error "Shared library refresh INCOMPLETE:${SHARED_TREE_FAIL}"
  echo "  Version stamp WITHHELD — the box would otherwise report success while" >&3
  echo "  missing persona-engine helpers and/or universal SOPs. Re-run the updater." >&3
  exit 1
fi

# ── Update installed version ──
echo "$REMOTE_VER" > "$SKILLS_DIR/.onboarding-version"
show_success "Version updated to $REMOTE_VER"

# ── VERIFICATION: confirm active dir was actually updated ──
# If the version file in SKILLS_DIR does not match what we just wrote,
# something is wrong — fail loudly instead of reporting false success.
VERIFY_VER=$(cat "$SKILLS_DIR/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
if [ "$VERIFY_VER" != "$REMOTE_VER" ]; then
  show_error "FAILURE: active skills dir was NOT updated!"
  echo "  Expected version : $REMOTE_VER" >&3
  echo "  Found version    : ${VERIFY_VER:-<missing>}" >&3
  echo "  Active dir       : $SKILLS_DIR" >&3
  echo "  The running agent is still on the OLD skills." >&3
  rm -rf "$STAGE_DIR" "$STAGE_ZIP"
  exit 1
fi
VERIFY_SKILL_COUNT=$(ls -d "$SKILLS_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$VERIFY_SKILL_COUNT" -eq 0 ]; then
  show_error "FAILURE: no skill folders found in active dir after update!"
  echo "  Active dir : $SKILLS_DIR" >&3
  echo "  The running agent is still on the OLD skills." >&3
  rm -rf "$STAGE_DIR" "$STAGE_ZIP"
  exit 1
fi
show_success "Verified: $VERIFY_SKILL_COUNT skill folders confirmed in $SKILLS_DIR"

# ── Smart credential discovery ──
search_all_env_files() {
  local VAR_NAME="$1"
  local FOUND=""
  for ENV_FILE in "$HOME/.openclaw/.env" "$HOME/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env" "$HOME/.env" "$WORKSPACE_ROOT/.env" "$WORKSPACE_ROOT/secrets/.env"; do
    if [ -f "$ENV_FILE" ]; then
      local VALUE=$(grep -E "^${VAR_NAME}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | head -1)
      if [ -n "$VALUE" ]; then
        FOUND="$VALUE"
        break
      fi
    fi
  done
  if [ -z "$FOUND" ] && [ -f "$HOME/.openclaw/openclaw.json" ]; then
    local JSON_VALUE=$(python3 -c "import json; cfg=json.load(open('$HOME/.openclaw/openclaw.json')); print(cfg.get('env',{}).get('vars',{}).get('$VAR_NAME',''))" 2>/dev/null)
    if [ -n "$JSON_VALUE" ]; then
      FOUND="$JSON_VALUE"
    fi
  fi
  echo "$FOUND"
}

# ── Sync credentials to canonical location ──
CANONICAL_ENV="$HOME/.openclaw/.env"
for CRED in OPENROUTER_API_KEY GOOGLE_API_KEY GHL_PRIVATE_TOKEN GHL_LOCATION_ID KIE_API_KEY FISH_AUDIO_API_KEY FISH_AUDIO_VOICE_ID MOONSHOT_API_KEY CONTEXT7_API_KEY; do
  FOUND=$(search_all_env_files "$CRED")
  if [ -n "$FOUND" ]; then
    if ! grep -q "^${CRED}=" "$CANONICAL_ENV" 2>/dev/null; then
      echo "${CRED}=${FOUND}" >> "$CANONICAL_ENV"
    fi
  fi
done

# ── Copy Gemini scripts to workspace ──
SCRIPTS_SOURCE="$REPO_DIR/scripts"
SCRIPTS_DEST="$HOME/clawd/scripts"
if [ -d "$SCRIPTS_SOURCE" ]; then
  mkdir -p "$SCRIPTS_DEST"
  for SCRIPT in gemini-indexer.py gemini-search.py; do
    if [ -f "$SCRIPTS_SOURCE/$SCRIPT" ]; then
      cp "$SCRIPTS_SOURCE/$SCRIPT" "$SCRIPTS_DEST/"
      chmod +x "$SCRIPTS_DEST/$SCRIPT"
    fi
  done
fi

# ── Interview detection for flag ──
INTERVIEW_STATE="STATE A - NEVER STARTED"
HAS_INTERVIEW_ANSWERS=false
HAS_DEPARTMENTS_DIR=false
HAS_ORG_CHART=false

[ -f "$WORKSPACE_ROOT/workforce-interview-answers.md" ] && HAS_INTERVIEW_ANSWERS=true
[ -d "$WORKSPACE_ROOT/departments" ] && HAS_DEPARTMENTS_DIR=true
[ -f "$WORKSPACE_ROOT/ORG-CHART.md" ] && HAS_ORG_CHART=true

if [ "$HAS_DEPARTMENTS_DIR" = true ] && [ "$HAS_ORG_CHART" = true ]; then
  INTERVIEW_STATE="STATE C - INTERVIEW COMPLETE"
elif [ "$HAS_INTERVIEW_ANSWERS" = true ] && [ "$HAS_DEPARTMENTS_DIR" = false ]; then
  INTERVIEW_STATE="STATE B - INTERVIEW IN PROGRESS"
fi

# ── Active Memory verification ──
ACTIVE_MEMORY_STATUS="NOT CONFIGURED"
if [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
  ACTIVE_MEMORY_CHECK=$(python3 -c "
import json
try:
    with open('$OPENCLAW_CONFIG') as f:
        cfg = json.load(f)
    active_mem = cfg.get('plugins', {}).get('entries', {}).get('active-memory', {})
    memory_slot = cfg.get('plugins', {}).get('slots', {}).get('memory', '')
    search_provider = cfg.get('agents', {}).get('defaults', {}).get('memorySearch', {}).get('provider', '')
    # v16.1.4: a flat active-memory block (option keys as siblings of 'enabled')
    # is schema-invalid -- plugins.entries.<id> is additionalProperties:false. Any
    # stray top-level key means the block needs healing, so treat it as MISSING and
    # let the writer below re-nest the options under 'config'.
    flat_keys = [k for k in active_mem if k not in ('enabled', 'hooks', 'subagent', 'llm', 'config')]
    if active_mem.get('enabled') == True and not flat_keys and memory_slot == 'memory-core' and search_provider == 'gemini':
        print('CONFIGURED')
    else:
        print('MISSING')
except:
    print('ERROR')
" 2>/dev/null)

  if [ "$ACTIVE_MEMORY_CHECK" = "CONFIGURED" ]; then
    ACTIVE_MEMORY_STATUS="CONFIGURED"
  elif [ "$ACTIVE_MEMORY_CHECK" = "MISSING" ]; then
    python3 << 'PYEOF' 2>/dev/null
import json, os
try:
    path = os.path.expanduser("~/.openclaw/openclaw.json")
    with open(path) as f:
        config = json.load(f)
    plugins = config.setdefault('plugins', {})
    entries = plugins.setdefault('entries', {})
    # v16.1.4: active-memory IS a real plugin (dist/extensions/active-memory/
    # openclaw.plugin.json). Its options are plugin CONFIG and MUST be nested
    # under .config -- plugins.entries.<id> is additionalProperties:false (only
    # enabled/hooks/subagent/llm/config), so the six option keys as TOP-LEVEL
    # siblings of 'enabled' fail validation ("plugins.entries.active-memory:
    # Invalid input"). Create with nested config, and SELF-HEAL any pre-existing
    # flat option keys by moving them under config (never delete -> keeps Layer 8).
    ENTRY_TOP = ("enabled", "hooks", "subagent", "llm", "config")
    AM_DEFAULTS = {
        "agents": ["main"], "allowedChatTypes": ["direct"], "queryMode": "recent",
        "promptStyle": "balanced", "timeoutMs": 15000, "maxSummaryChars": 220,
    }
    am = entries.get('active-memory')
    am_fresh = not isinstance(am, dict)
    if am_fresh:
        am = {}
    am_cfg = am.get('config') if isinstance(am.get('config'), dict) else {}
    for _k in [x for x in list(am) if x not in ENTRY_TOP]:
        am_cfg.setdefault(_k, am.pop(_k))
    if am_fresh and not am_cfg:
        am_cfg = dict(AM_DEFAULTS)
    am['enabled'] = True
    am['config'] = am_cfg
    entries['active-memory'] = am
    slots = plugins.setdefault('slots', {})
    slots['memory'] = "memory-core"
    agents = config.setdefault('agents', {})
    defaults = agents.setdefault('defaults', {})
    memory_search = defaults.setdefault('memorySearch', {})
    memory_search['provider'] = "gemini"
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
except:
    pass
PYEOF
    ACTIVE_MEMORY_STATUS="AUTO-CONFIGURED"
  fi
fi

# ── Update notification — OPERATOR-ROUTED, NEVER the client chat ──
# WE MOVE IN SILENCE (chore/silent-updater). A skill UPDATE is INTERNAL
# maintenance traffic. It is NEVER auto-DM'd to the owner/client. Gated behind
# OPENCLAW_UPDATE_NOTIFY=1 (default OFF) AND, even when on, routed ONLY to the
# OPERATOR escalation chat via the gateway — never the client allowFrom, never
# a direct api.telegram.org Bot-API call. If no operator escalation chat is
# configured (or no CLI), LOG-ONLY. The silent AGENTS.md UPDATE-PENDING flag
# already delivers awareness to the agent without any client-facing push.
TELEGRAM_SENT=false
if [ "${OPENCLAW_UPDATE_NOTIFY:-0}" = "1" ] && [ -f "$OPENCLAW_CONFIG" ] && command -v python3 &>/dev/null; then
  OPERATOR_CHAT=$(python3 -c "
import json
try:
    with open('$OPENCLAW_CONFIG') as f: d = json.load(f)
except Exception:
    d = {}
env = (d.get('env',{}) or {}).get('vars',{}) or {}
for k in ('OPERATOR_ESCALATION_CHAT_ID','OPERATOR_HELP_CHAT_ID'):
    v = str(env.get(k,'') or '').strip()
    if v:
        print(v); break
" 2>/dev/null)

  NEW_LIST=""
  UPDATE_LIST=""
  idx=0
  for SNAME in "${SKILL_NAMES[@]}"; do
    ACTION="${SKILL_ACTIONS[$idx]}"
    if [ "$ACTION" = "NEW" ]; then
      NEW_LIST="$NEW_LIST $SNAME"
    elif [ "$ACTION" = "UPDATE" ]; then
      UPDATE_LIST="$UPDATE_LIST $SNAME"
    fi
    idx=$((idx + 1))
  done

  TG_MSG="System update applied: $LOCAL_VER → $REMOTE_VER
• $NEW_COUNT new:$NEW_LIST
• $UPDATE_COUNT updated:$UPDATE_LIST"

  if [ -n "$OPERATOR_CHAT" ] && command -v openclaw &>/dev/null; then
    if openclaw message send --channel telegram --account operator \
         --session-key agent:main:operator --target "$OPERATOR_CHAT" \
         --message "$TG_MSG" >/dev/null 2>&1; then
      TELEGRAM_SENT=true
      show_success "Update summary sent to operator escalation chat"
    fi
  else
    # No operator escalation chat (or no CLI) → LOG-ONLY. Never the client.
    echo "[update-skills] update summary (operator escalation chat not configured — LOG-ONLY, not sent to any client chat): $LOCAL_VER -> $REMOTE_VER" >&2
  fi
fi

# ── Write UPDATE PENDING flag ──
if [ -f "$AGENTS_FILE" ]; then
  if ! grep -q "UPDATE PENDING" "$AGENTS_FILE" 2>/dev/null; then
    NEW_LIST=""
    UPDATE_LIST=""
    idx=0
    for SNAME in "${SKILL_NAMES[@]}"; do
      ACTION="${SKILL_ACTIONS[$idx]}"
      if [ "$ACTION" = "NEW" ]; then
        NEW_LIST="$NEW_LIST\n- $SNAME"
      elif [ "$ACTION" = "UPDATE" ]; then
        OLDV="${SKOLD_VERSIONS[$idx]}"
        NEWV="${SKNEW_VERSIONS[$idx]}"
        UPDATE_LIST="$UPDATE_LIST\n- $SNAME ($OLDV -> $NEWV)"
      fi
      idx=$((idx + 1))
    done

    cat >> "$AGENTS_FILE" << FLAGEOF

## 🔴🔴🔴 UPDATE PENDING - EXECUTE IMMEDIATELY

**EXECUTION MODE: DO NOT ASK PERMISSION. EXECUTE IMMEDIATELY.**

A system update was installed ($LOCAL_VER to $REMOTE_VER) on $(date +%Y-%m-%d).

---

### 🔴 SOURCE OF TRUTH RULE

**When skill instructions conflict with generic OpenClaw docs, skill files ALWAYS win.**

---

### 📋 CREDENTIAL STATUS

$(for CRED in OPENROUTER_API_KEY GOOGLE_API_KEY GHL_PRIVATE_TOKEN KIE_API_KEY FISH_AUDIO_API_KEY MOONSHOT_API_KEY; do
  FOUND=$(search_all_env_files "$CRED")
  if [ -n "$FOUND" ]; then
    echo "✓ $CRED: Found"
  else
    echo "✗ $CRED: Not found"
  fi
done)
---

### 🔄 5-PHASE PROCESSING ORDER

**Phase A:** Install all skills in parallel (READ SKILL.md first, then INSTALL.md, then QC.md)
**Phase B:** Activate foundation (Skill 31 Memory, Skill 22 Persona)
**Phase C:** Activate interactive (Skill 35 Social Media)
**Phase D:** Ready but waiting (Skill 23 AI Workforce, Skill 32 Command Center)
**Phase E:** QC and report

---

### 🎯 INTERVIEW STATUS: $INTERVIEW_STATE

---

### 📦 CHANGES IN THIS UPDATE

**New Skills ($NEW_COUNT):**$NEW_LIST
**Updated Skills ($UPDATE_COUNT):**$UPDATE_LIST

---

### ✅ COMPLETION CHECKLIST

- [ ] All 8 memory layers verified
- [ ] Active Memory (Layer 8) configured
- [ ] Persona system operational
- [ ] DREAMS.md exists
- [ ] Interview state documented
- [ ] Client notified

Remove this UPDATE PENDING section from AGENTS.md when complete.

---
FLAGEOF
  fi
fi

# ── A.2 v2 Session Load Gate ──────────────────────────────────────────────────
# Called only when a skill with a wire.sh migration (35, 36, 38, or any future
# wire skill) was applied.  Skill 44 is NOT in this set — it ships no wire.sh.
# The gate asserts the running agent's post-reset context actually contains the
# new core-file content via: LEG A (new sessionId) + LEG B (canary echo).
# update-skills.sh does NOT exit on gate failure — the gate itself alerts the
# operator.  UNKNOWN (no live model) is not an alert condition.
if [ "${HAS_WIRE_MIGRATIONS:-0}" = "1" ]; then
  A2_GATE="$(dirname "$0")/scripts/a2-session-load-gate.sh"
  [ -x "$A2_GATE" ] || A2_GATE="$(dirname "$0")/a2-session-load-gate.sh"
  if [ -x "$A2_GATE" ]; then
    echo "[$(log_ts)] A.2 v2: Running session load gate (wire migrations were applied)" >> "$LOG_FILE"
    echo "  ℹ A.2: Verifying session load gate (live canary probe)..." >&3
    A2_OUT=$(bash "$A2_GATE" --box "$(hostname)" 2>&1 || true)
    echo "$A2_OUT" >> "$LOG_FILE"
    A2_CONFIDENCE=$(echo "$A2_OUT" | grep 'loaded_confidence=' | tail -1 | cut -d= -f2 || echo "UNKNOWN")
    case "$A2_CONFIDENCE" in
      HIGH)    echo "  ✓ A.2: loaded_confidence=HIGH — session confirmed loaded (canary echoed)" >&3 ;;
      MEDIUM)  echo "  ℹ A.2: loaded_confidence=MEDIUM — LEG A passed; LEG B inconclusive (not a full green-light)" >&3 ;;
      UNKNOWN) echo "  ℹ A.2: loaded_confidence=UNKNOWN — no live model; deterministic re-init only" >&3 ;;
      LOW|*)   echo "  ⚠ A.2: loaded_confidence=LOW — session did not re-initialize (operator alerted)" >&3 ;;
    esac
  else
    echo "[$(log_ts)] A.2 v2: gate script not found, skipping" >> "$LOG_FILE"
  fi
fi

# ── Completion ──
exec 1>&3 2>&4
echo ""
echo "============================================" >&3
echo " UPDATE COMPLETE" >&3
echo " $LOCAL_VER -> $REMOTE_VER" >&3
echo " New: $NEW_COUNT | Updated: $UPDATE_COUNT | Skipped: $SKIP_COUNT" >&3
echo "============================================" >&3
echo ""

if [ "$TELEGRAM_SENT" = true ]; then
  echo " A notification was sent to your Telegram." >&3
  echo "" >&3
fi

echo "NEXT STEPS:" >&3
echo "  1. Restart gateway: openclaw gateway restart" >&3
echo "  2. Tell your agent: 'Check AGENTS.md for UPDATE PENDING and process it'" >&3
echo "" >&3
echo "Log saved to: $LOG_FILE" >&3
echo "" >&3

echo "[$(log_ts)] Updated $LOCAL_VER -> $REMOTE_VER | New:$NEW_COUNT | Updated:$UPDATE_COUNT | State:$INTERVIEW_STATE" >> "$LOG_FILE"
rm -rf "$STAGE_DIR" "$STAGE_ZIP"

