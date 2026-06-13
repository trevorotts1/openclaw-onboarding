#!/usr/bin/env bash
# ============================================================
#  OpenClaw Skills Updater -- Unified (Mac + VPS)
#  PRD 2.1 -- unified repo (trevorotts1/openclaw-onboarding)
#
#  Platform auto-detected via OPENCLAW_PLATFORM env var or presence of /data/.openclaw.
#  VPS: sources platform/vps/bootstrap.sh for container re-exec + path setup.
#  Mac: sources platform/mac/bootstrap.sh for Homebrew prereqs + path setup.
# ============================================================

# Platform detection + bootstrap (MUST run before set -euo pipefail -- VPS container
# re-exec uses conditional commands that may fail intentionally).
_DETECT_PLATFORM="${OPENCLAW_PLATFORM:-}"
if [ -z "$_DETECT_PLATFORM" ]; then
    [ -d "/data/.openclaw" ] && _DETECT_PLATFORM="vps" || _DETECT_PLATFORM="mac"
fi
export OPENCLAW_PLATFORM="$_DETECT_PLATFORM"

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
_PLATFORM_BOOTSTRAP="${_SCRIPT_DIR}/platform/${OPENCLAW_PLATFORM}/bootstrap.sh"
if [ -f "$_PLATFORM_BOOTSTRAP" ]; then
    # shellcheck source=/dev/null
    source "$_PLATFORM_BOOTSTRAP"
else
    # Inline minimal fallback when running via curl (no local clone yet).
    if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
        OC_PLATFORM="vps"; OC_CONFIG="/data/.openclaw"; OC_JSON="/data/.openclaw/openclaw.json"
        OC_SKILLS_DIR="/data/.openclaw/skills"; OC_WORKSPACE_DEFAULT="/data/.openclaw/workspace"
    else
        OC_PLATFORM="mac"; OC_CONFIG="$HOME/.openclaw"; OC_JSON="$HOME/.openclaw/openclaw.json"
        OC_SKILLS_DIR="$HOME/.openclaw/skills"; OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"
    fi
fi

set -euo pipefail

ONBOARDING_VERSION="v12.3.5"

LOG_FILE="/tmp/openclaw-update-$(date +%Y%m%d-%H%M%S).log"

# ----------------------------------------------------------
# Telegram Progress Notification (mirrors install.sh)
# ----------------------------------------------------------
TELEGRAM_LAST_RESULT=""
send_telegram_progress() {
  local message="$1"
  local OCJSON="$HOME/.openclaw/openclaw.json"
  local TELEGRAM_TARGET=""
  TELEGRAM_LAST_RESULT="skipped"

  if [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
    TELEGRAM_TARGET=$(python3 -c "
import json
try:
    cfg = json.load(open('$OCJSON'))
    allow = cfg.get('channels', {}).get('telegram', {}).get('allowFrom', [])
    if allow:
        print(allow[0])
except:
    pass
" 2>/dev/null)
  fi

  if ! command -v openclaw >/dev/null 2>&1; then
    TELEGRAM_LAST_RESULT="no-openclaw-cli"
    return 0
  fi
  if [ -z "$TELEGRAM_TARGET" ]; then
    TELEGRAM_LAST_RESULT="no-telegram-target"
    return 0
  fi
  if openclaw message send --channel telegram --target "$TELEGRAM_TARGET" --message "$message" >> "$LOG_FILE" 2>&1; then
    TELEGRAM_LAST_RESULT="sent:$TELEGRAM_TARGET"
  else
    TELEGRAM_LAST_RESULT="failed:see-$LOG_FILE"
  fi
}

# ----------------------------------------------------------
# Write UPDATE PENDING flag to AGENTS.md
# ----------------------------------------------------------
write_update_pending_flag() {
  local version="$1"
  local new_skills="$2"

  # v10.15.48: resolve the canonical workspace the agent ACTUALLY reads from.
  # Prefer the OBS-resolved workspace (per-agent override -> defaults ->
  # canonical default). NEVER prefer the dead ~/clawd -- writing the flag there
  # while the agent reads ~/.openclaw/workspace is the classic "agent never sees
  # the flag" bug. Falls back to the canonical default only.
  local WORKSPACE_DIR=""
  if command -v obs_resolve_workspace >/dev/null 2>&1; then
    WORKSPACE_DIR="$(obs_resolve_workspace)"
  fi
  [ -z "$WORKSPACE_DIR" ] && WORKSPACE_DIR="$HOME/.openclaw/workspace"
  mkdir -p "$WORKSPACE_DIR"
  local AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"

  touch "$AGENTS_FILE"
  # FIX 1: FULLY strip ALL prior UPDATE PENDING / ONBOARDING PENDING SECTIONS
  # (header → next "## " heading or EOF). The old `grep -v "UPDATE PENDING"`
  # only removed the single header LINE, leaving the multi-line body behind and
  # STACKING a fresh full flag on every run -- duplicates accreted forever.
  AGENTS_FILE="$AGENTS_FILE" python3 - <<'PYEOF' 2>/dev/null || true
import os, re
p = os.environ["AGENTS_FILE"]
try:
    text = open(p, encoding="utf-8", errors="replace").read()
except Exception:
    text = ""
# Remove any "## ... UPDATE PENDING ..." or "## ... ONBOARDING PENDING ..."
# section: from its "## " header up to (but not including) the next top-level
# "## " heading, or EOF. Non-greedy, multiline.
pattern = re.compile(
    r'(?m)^##[^\n]*(?:UPDATE PENDING|ONBOARDING PENDING)[^\n]*\n'   # the header
    r'(?:(?!^##\s).*\n?)*',                                         # body until next "## "
)
new = pattern.sub("", text)
# Collapse >2 blank lines left behind.
new = re.sub(r'\n{3,}', '\n\n', new)
open(p, "w", encoding="utf-8").write(new)
PYEOF

  local DATE_STAMP
  DATE_STAMP=$(date +%Y-%m-%d)

  cat >> "$AGENTS_FILE" <<FLAGCONTENT

## 🔴🔴🔴 UPDATE PENDING -- SKILL UPDATE TO ${version}

**EXECUTION MODE: DO NOT ASK PERMISSION. EXECUTE IMMEDIATELY.**

A skill update was applied via update-skills.sh on ${DATE_STAMP}. Process the activation steps now.

### 🔴 THE GATE IS THE TRUTH -- NOT THIS PROSE, NOT YOUR OWN "done"
This update is **NOT complete** until the VERIFICATION GATE passes. Files on disk = DOWNLOADED, not installed. Source the gate and check state:
- State file: \`~/.openclaw/workspace/.onboarding-state.json\` (per-skill: pending → downloaded → wired → qc-passed | qc-failed)
- Gate library: \`~/.openclaw/scripts/onboarding-state.sh\` (or the onboarding repo's \`scripts/\`)
- Run: source the library, then \`obs_gate_summary\`. A skill counts INSTALLED only when (a) \`openclaw skills info <name>\` shows it, (b) its CORE_UPDATES sentinel is present (if it ships CORE_UPDATES.md), and (c) its \`qc-*.sh\` exits 0 (if it ships one).
- **NEVER tell the owner "installed / done / onboarded" for any skill that is not \`qc-passed\` (or an explicit INTERVIEW_PENDING park).**

### What changed in this update
- Onboarding version: ${version}
- New skills installed (require ACTIVATION + GATE): ${new_skills:-none -- updates only}

### How to process each skill that is NOT yet qc-passed
For each such skill folder under \`~/.openclaw/skills/\`:
1. READ all files (Teach Yourself Protocol): SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md, plus any \`references/*.md\` files
2. CHECK prerequisites and search ALL standard credential locations (canonical: \`~/.openclaw/secrets/.env\` on Mac, \`/data/.openclaw/secrets/.env\` on VPS, plus \`openclaw.json\` env.vars). Skip asking the owner if values already exist.
3. EXECUTE the activation steps in INSTALL.md (read ≠ execute)
4. APPLY CORE_UPDATES.md surgically -- add to AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md only the sections explicitly labeled in that file
5. RUN the gate (\`obs_verify_skill <folder>\`); loop activate→verify until it returns \`qc-passed\`. Skills that legitimately await owner input may be parked \`interview-pending\` (re-ping the owner; do NOT treat as terminal "done").
6. REPORT to owner ONLY what is verified-installed, plus what remains gated.

### Discipline (binding)
- Skills 22-23: MAIN ORCHESTRATOR ONLY, never delegate
- Tier order in any tiered skill (e.g. skill 36 GHL MCP): try Tier N before Tier N+1, no skipping
- Disclosure headers (e.g. \`[GHL tier used: N -- tool_name]\`) required per any skill's SOUL-level rules
- No destructive shortcuts: no \`--force\`, no \`--no-verify\`, no \`--break-system-packages\` unless explicitly instructed

### When the GATE passes (and ONLY then)
- Remove this entire UPDATE PENDING section from AGENTS.md
- Add to MEMORY.md under "## System Updates":
  "${version} update applied on ${DATE_STAMP}. Verification gate PASSED. Skills activated: ${new_skills:-none}."

FLAGCONTENT
  echo "  ✓ UPDATE PENDING flag written (deduped) to $AGENTS_FILE"

  # Seed Core.md terminology into MEMORY.md (idempotent)
  local MEMORY_FILE="$WORKSPACE_DIR/MEMORY.md"
  touch "$MEMORY_FILE"
  if ! grep -q "## Terminology -- Core.md Files" "$MEMORY_FILE" 2>/dev/null; then
    cat >> "$MEMORY_FILE" << 'COREMDEOF'

## Terminology -- Core.md Files

When the owner says **"Core.md files"** they mean the OpenClaw bootstrap files loaded every session -- not a literal file called `core.md`. The Core.md files are:

- **IDENTITY.md** -- the role the agent is playing. It contains the **experiences and the skills they need to embody** that role. Not just surface metadata (name / vibe / emoji) -- the lived background and capability set of the character being played.
- **SOUL.md** -- the **personality** of the agent, its **true mission**, its **beliefs**, its **rules**, its **goals**, its **belief systems**, its **principles**. Who the agent IS, not who they are playing. First file injected each session.
- **AGENTS.md** -- operating procedures, protocols, workflows, memory rules. *What the agent does and how*
- **USER.md** -- the human being helped (name, timezone, preferences, communication style)
- **TOOLS.md** -- local tool notes and conventions (camera names, SSH aliases, environment-specific specifics) -- NOT a permissions registry
- **MEMORY.md** -- curated long-term durable facts, decisions, preferences. Loaded in main private sessions; paired with daily logs at `memory/YYYY-MM-DD.md`

When the owner says "update the Core.md files" or "this needs to live in the Core.md files," choose the right one of these six based on its purpose:
- Personality / principle → SOUL.md
- Procedure / workflow → AGENTS.md
- Tool note → TOOLS.md
- Durable fact / decision → MEMORY.md
- User info → USER.md
- Identity metadata → IDENTITY.md

Never interpret "Core.md" as a literal filename.

COREMDEOF
    echo "  ✓ Core.md terminology seeded into MEMORY.md"
  fi
}

# ----------------------------------------------------------
# SKILLS DIRECTORY SECTION -- Active-dir-first detection
# ----------------------------------------------------------
# Platform detection:
#   VPS  (Hostinger Docker) → active dir is /data/.openclaw/skills
#   Mac                     → active dir is ~/.openclaw/skills
# We ALWAYS prefer the directory the running agent actually loads,
# falling back to ~/Downloads/openclaw-master-files only when the
# active dir doesn't exist.  Updating a stale Downloads copy while
# the active dir is untouched is a silent no-op (the classic bug).
# ----------------------------------------------------------

# ----------------------------------------------------------
# Discover skills directory -- active dir first
# ----------------------------------------------------------
discover_skills_dir() {
  # Detect platform: VPS has /data, Mac does not
  if [ -d /data ]; then
    # VPS (Hostinger Docker) -- active path is /data/.openclaw/skills
    local ACTIVE_DIR="/data/.openclaw/skills"
  else
    # Mac -- active path is ~/.openclaw/skills
    local ACTIVE_DIR="$HOME/.openclaw/skills"
  fi

  # Use the active dir whenever it exists and is non-empty
  if [ -d "$ACTIVE_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$ACTIVE_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$ACTIVE_DIR"
      return
    fi
  fi

  # Active dir exists but is empty (first-install into it) -- still prefer it
  if [ -d "$ACTIVE_DIR" ]; then
    echo "$ACTIVE_DIR"
    return
  fi

  # Fallback: check Downloads copy (legacy / pre-active-dir installs)
  local LEGACY_DIR="$HOME/Downloads/openclaw-master-files"
  if [ -d "$LEGACY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$LEGACY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$LEGACY_DIR"
      return
    fi
  fi

  # Fuzzy search for folders with "openclaw" and "master" in name (case-insensitive)
  local FUZZY_DIR=$(find "$HOME" -maxdepth 2 -type d -iname "*openclaw*" 2>/dev/null | grep -i "master" | head -1)
  if [ -n "$FUZZY_DIR" ] && [ -d "$FUZZY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$FUZZY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$FUZZY_DIR"
      return
    fi
  fi

  # Last resort: create and target the active dir (fresh install)
  echo "$ACTIVE_DIR"
}

# ----------------------------------------------------------
# UPDATE PENDING flag handling -- search correct locations
# ----------------------------------------------------------
check_update_pending() {
  # Search Mac primary location first, then secondary
  local PENDING_PATHS=(
    "$HOME/Downloads/openclaw-master-files/.pending-setup.md"
    "$HOME/.openclaw/skills/.pending-setup.md"
    "$HOME/.openclaw/onboarding/.pending-setup.md"
  )

  for PENDING in "${PENDING_PATHS[@]}"; do
    if [ -f "$PENDING" ]; then
      echo "$PENDING"
      return
    fi
  done

  # Return empty if not found
  echo ""
}

# ----------------------------------------------------------
# Check .onboarding-version -- search multiple paths
# Priority MUST match discover_skills_dir() (active dir first, legacy second)
# so the version we READ is the same location we WRITE to. If the legacy
# Downloads path is checked first the script sees the old stale marker even
# after a successful update → perpetual "needs update" false-positive (Bug B).
# ----------------------------------------------------------
get_current_version() {
  # Active dir first (mirrors discover_skills_dir priority)
  local VERSION_PATHS=(
    "$HOME/.openclaw/skills/.onboarding-version"
    "$HOME/Downloads/openclaw-master-files/.onboarding-version"
    "$HOME/.openclaw/onboarding/.onboarding-version"
  )

  for VERSION_FILE in "${VERSION_PATHS[@]}"; do
    if [ -f "$VERSION_FILE" ]; then
      cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]'
      return
    fi
  done

  # Return empty if not found
  echo ""
}

# ----------------------------------------------------------
# v12.3.5 - safe_json_edit
# Harden any direct write to openclaw.json: back up, apply the
# python3 transform, validate with `openclaw config validate`,
# and ROLL BACK from the backup on failure so one bad key can
# never abort the updater under set -euo pipefail.
#
# The root-cause bug that aborted Corey + Maria's update was
# skills.path written into openclaw.json on VPS (2026.5.x rejects
# the key with "skills Unrecognized key path / skills Invalid input").
# This helper ensures any future json edits are validated before they
# can corrupt the config and kill the run.
#
# Usage:
#   safe_json_edit OCJSON_PATH DESCRIPTION python3_transform_func
# where python3_transform_func is a bash function that:
#   - receives OCJSON_PATH as $1
#   - edits the file in-place
#   - exits 0 on success, non-zero on failure
#
# Note: the Mac updater has NO direct json.dump writes today --
# GHL MCP wiring uses `openclaw mcp set` which validates its own
# input. This helper is provided here as a forward-defense guard
# so future changes are forced to go through validation + rollback.
# ----------------------------------------------------------
safe_json_edit() {
  local OCJSON="$1"
  local DESCRIPTION="${2:-openclaw.json edit}"
  local EDIT_FUNC="$3"

  if [ ! -f "$OCJSON" ]; then
    echo "  [safe_json_edit] $OCJSON not found -- skipping $DESCRIPTION"
    return 0
  fi

  local BACKUP="${OCJSON}.bak-$(date +%Y%m%d-%H%M%S)"
  cp -f "$OCJSON" "$BACKUP" 2>/dev/null || {
    echo "  [safe_json_edit] WARN: could not create backup -- skipping $DESCRIPTION"
    return 0
  }

  # Run the edit function
  if ! "$EDIT_FUNC" "$OCJSON"; then
    echo "  [safe_json_edit] WARN: edit function failed -- rolling back $DESCRIPTION"
    cp -f "$BACKUP" "$OCJSON" 2>/dev/null || true
    rm -f "$BACKUP" 2>/dev/null || true
    return 0
  fi

  # Validate with the CLI if available
  if command -v openclaw >/dev/null 2>&1; then
    if ! openclaw config validate >> "$LOG_FILE" 2>&1; then
      echo "  [safe_json_edit] WARN: openclaw config validate FAILED after $DESCRIPTION -- rolling back"
      cp -f "$BACKUP" "$OCJSON" 2>/dev/null || true
      rm -f "$BACKUP" 2>/dev/null || true
      return 0
    fi
  fi

  rm -f "$BACKUP" 2>/dev/null || true
  echo "  [safe_json_edit] $DESCRIPTION applied and validated OK"
}

# ----------------------------------------------------------
# v10.15.51 -- link_shared_core_files
# ----------------------------------------------------------
# Zero-Human-Workforce file model: on EVERY box, ALL of that account's agents
# + sub-agents SHARE the box's ONE canonical AGENTS.md / TOOLS.md / USER.md
# (symlinked, NOT duplicated). Per-agent files (IDENTITY.md, SOUL.md, MEMORY.md,
# HEARTBEAT.md) stay each agent's OWN real files -- never touched here (except
# additive content preservation into IDENTITY.md, see below).
#
# CANON_DIR = the box's DEFAULT AGENT WORKSPACE (agents.defaults.workspace, with
# the same resolver as obs_resolve_workspace / install.sh Step 10). The canonical
# AGENTS.md/TOOLS.md/USER.md live there. The symlink target is ALWAYS this LOCAL
# box's own canonical -- NEVER a hardcoded path and NEVER a cross-box/cross-account
# path. The client is the USER; a client box links to the CLIENT's own files only.
# This is the co-mingling guard (N0): we read THIS box's openclaw.json and resolve
# THIS box's workspace -- we never write a foreign path into a client's symlink.
#
# NESTED WORKFLOW AGENT EXEMPTION: any workspace path matching */workflows/*/agents/*
# is an internal workflow micro-agent and is NEVER touched.
#
# Idempotent: a second run produces no new backups and no churn -- a symlink that
# already points at CANON_DIR/<f> is a no-op; an absent file is left absent.
# Every action is logged with the [link-shared] prefix.
# ----------------------------------------------------------
link_shared_core_files() {
  local CANON_DIR="${1:-}"

  # --- Resolve CANON_DIR (box's own default agent workspace) ---------------
  # Precedence mirrors obs_resolve_workspace / install.sh Step 10:
  #   per-agent main override -> agents.defaults.workspace -> ~/.openclaw/workspace.
  # We ALWAYS read THIS box's openclaw.json -- never a foreign/hardcoded path.
  local OCJSON="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && OCJSON="/data/.openclaw/openclaw.json"
  if [ -z "$CANON_DIR" ]; then
    if command -v obs_resolve_workspace >/dev/null 2>&1; then
      CANON_DIR="$(obs_resolve_workspace)"
    elif [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
      CANON_DIR="$(OC_JSON="$OCJSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict) and ag.get("id") == "main" and ag.get("workspace"):
            print(os.path.expanduser(ag["workspace"])); break
    else:
        ws = cfg.get("agents", {}).get("defaults", {}).get("workspace")
        if ws:
            print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
)"
    fi
  fi
  # Final fallback: the canonical OpenClaw default for this box. (Clawd is dead;
  # only fall back to ~/clawd as an absolute last resort if it is the workspace.)
  if [ -z "$CANON_DIR" ]; then
    if [ -d "/data/.openclaw" ]; then
      CANON_DIR="/data/.openclaw/workspace"
    else
      CANON_DIR="$HOME/.openclaw/workspace"
    fi
  fi

  echo "  [link-shared] Zero-Human-Workforce file unification"
  echo "  [link-shared] CANON_DIR (this box's own canonical) = $CANON_DIR"
  mkdir -p "$CANON_DIR" 2>/dev/null || true

  # The canonical files must exist before we can link to them. touch ensures a
  # symlink target is always present (empty is fine; later wiring fills them).
  local f
  for f in AGENTS.md TOOLS.md USER.md; do
    [ -e "$CANON_DIR/$f" ] || { touch "$CANON_DIR/$f" 2>/dev/null || true; }
  done

  # Resolve CANON_DIR to an absolute, symlink-free real path so comparisons and
  # link targets are stable + correct.
  local CANON_REAL
  CANON_REAL="$(cd "$CANON_DIR" 2>/dev/null && pwd -P || echo "$CANON_DIR")"

  local TS
  TS="$(date +%Y%m%d-%H%M%S)"

  # --- Enumerate agent workspaces ------------------------------------------
  # Sources: (a) every agents[].workspace declared in THIS box's openclaw.json,
  # (b) a scan of the workspaces/ dir (immediate children + agents/* role dirs).
  # We only ever operate on dirs under this box. Dedup; skip CANON; skip nested workflow agents.
  local WS_LIST_FILE
  WS_LIST_FILE="$(mktemp 2>/dev/null || echo "/tmp/link-shared-ws-$$.txt")"
  : > "$WS_LIST_FILE"

  if [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
    OC_JSON="$OCJSON" python3 - >> "$WS_LIST_FILE" 2>/dev/null <<'PYEOF' || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict):
            ws = ag.get("workspace")
            if ws:
                print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
  fi

  # Scan the workspaces dir tree for agent-shaped dirs. The canonical default
  # parent is .openclaw/ (or /data/.openclaw); also scan the workspace's own
  # departments/ + agents/ trees where role workspaces live.
  local OC_ROOT="$HOME/.openclaw"
  [ -d "/data/.openclaw" ] && OC_ROOT="/data/.openclaw"
  local _scan
  for _scan in \
      "$OC_ROOT/workspaces" \
      "$CANON_REAL/agents" \
      "$CANON_REAL/departments"; do
    [ -d "$_scan" ] || continue
    # Any dir that already carries one of the shared files (real or link) is an
    # agent workspace candidate. find -type d then filter in the loop below.
    find "$_scan" -type d \( -name 'AGENTS.md' -prune \) -o -type d -print 2>/dev/null \
      | while IFS= read -r d; do
          if [ -e "$d/AGENTS.md" ] || [ -e "$d/IDENTITY.md" ] || [ -e "$d/SOUL.md" ]; then
            echo "$d"
          fi
        done >> "$WS_LIST_FILE" 2>/dev/null || true
  done

  local LINKED=0 REPOINTED=0 BACKED_UP=0 PRESERVED=0 SKIPPED_ANT=0 NOOP=0

  # Dedup workspace list, then process each.
  local W
  while IFS= read -r W; do
    [ -n "$W" ] || continue
    W="$(printf '%s' "$W" | sed 's:/*$::')"   # strip trailing slashes
    [ -d "$W" ] || continue

    # Resolve to absolute real path for a correct CANON comparison.
    local W_REAL
    W_REAL="$(cd "$W" 2>/dev/null && pwd -P || echo "$W")"

    # Skip the canonical workspace itself -- it OWNS the real files.
    if [ "$W_REAL" = "$CANON_REAL" ]; then
      continue
    fi

    # NESTED WORKFLOW AGENT EXEMPTION: never touch */workflows/*/agents/* micro-agents.
    case "$W_REAL/" in
      */workflows/*/agents/*)
        echo "  [link-shared] SKIP (nested workflow agent exempt): $W_REAL"
        SKIPPED_ANT=$((SKIPPED_ANT + 1))
        continue
        ;;
    esac

    for f in AGENTS.md TOOLS.md USER.md; do
      local TARGET="$CANON_REAL/$f"
      local LINKPATH="$W_REAL/$f"

      if [ -L "$LINKPATH" ]; then
        # Already a symlink -- repoint ONLY if it points somewhere wrong.
        local CUR
        CUR="$(readlink "$LINKPATH" 2>/dev/null || echo '')"
        # Resolve current target to a real path for comparison.
        local CUR_REAL
        CUR_REAL="$(cd "$(dirname "$LINKPATH")" 2>/dev/null && cd "$(dirname "$CUR")" 2>/dev/null && pwd -P 2>/dev/null)/$(basename "$CUR")"
        if [ "$CUR" = "$TARGET" ] || [ "$CUR_REAL" = "$TARGET" ]; then
          NOOP=$((NOOP + 1))   # idempotent: correct link, no churn
        else
          ln -sfn "$TARGET" "$LINKPATH" 2>/dev/null \
            && { echo "  [link-shared] REPOINT $LINKPATH -> $TARGET (was: $CUR)"; REPOINTED=$((REPOINTED + 1)); } \
            || echo "  [link-shared] WARN: could not repoint $LINKPATH"
        fi

      elif [ -f "$LINKPATH" ]; then
        # A REAL file. Back it up (NEVER delete), preserve unique content into
        # this agent's OWN IDENTITY.md (additive only), then replace with a link.
        local BAK="$LINKPATH.bak-unify-$TS"
        cp -p "$LINKPATH" "$BAK" 2>/dev/null \
          && { echo "  [link-shared] BACKUP $LINKPATH -> $BAK"; BACKED_UP=$((BACKED_UP + 1)); } \
          || { echo "  [link-shared] WARN: backup failed for $LINKPATH -- leaving file untouched"; continue; }

        # Best-effort PRESERVE: append any content NOT already in CANON/<f> to
        # this agent's OWN IDENTITY.md under a guarded marker (only ADD; create
        # IDENTITY.md if absent). Guard prevents duplicate preservation on re-run.
        local AGENT_NAME
        AGENT_NAME="$(basename "$W_REAL")"
        local IDFILE="$W_REAL/IDENTITY.md"
        local PMARK="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification ${TS}) -->"
        # Marker prefix (sans timestamp) used to detect prior preservation of the
        # same agent+file so re-runs never re-append.
        local PMARK_PREFIX="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification "
        if ! grep -qF "$PMARK_PREFIX" "$IDFILE" 2>/dev/null; then
          AGENT_F="$LINKPATH" CANON_F="$TARGET" ID_F="$IDFILE" PMARK="$PMARK" \
            python3 - <<'PYEOF' 2>/dev/null || true
import os
src   = os.environ["AGENT_F"]
canon = os.environ["CANON_F"]
idf   = os.environ["ID_F"]
mark  = os.environ["PMARK"]
try:
    src_text = open(src, encoding="utf-8", errors="replace").read()
except Exception:
    src_text = ""
try:
    canon_text = open(canon, encoding="utf-8", errors="replace").read()
except Exception:
    canon_text = ""
# Split the agent's file into blank-line-delimited blocks; keep only blocks
# whose stripped text is non-empty AND not already present in the canonical file.
blocks, cur = [], []
for line in src_text.splitlines():
    if line.strip() == "":
        if cur:
            blocks.append("\n".join(cur)); cur = []
    else:
        cur.append(line)
if cur:
    blocks.append("\n".join(cur))
unique = [b for b in blocks if b.strip() and b.strip() not in canon_text]
if unique:
    with open(idf, "a", encoding="utf-8") as fh:
        fh.write("\n\n" + mark + "\n")
        fh.write("\n\n".join(unique))
        fh.write("\n")
    print("PRESERVED")
PYEOF
          if grep -qF "$PMARK" "$IDFILE" 2>/dev/null; then
            echo "  [link-shared] PRESERVE unique $f content -> $IDFILE"
            PRESERVED=$((PRESERVED + 1))
          fi
        fi

        # Replace the real file with a symlink to the box's own canonical.
        rm -f "$LINKPATH" 2>/dev/null
        ln -sfn "$TARGET" "$LINKPATH" 2>/dev/null \
          && { echo "  [link-shared] LINK $LINKPATH -> $TARGET"; LINKED=$((LINKED + 1)); } \
          || echo "  [link-shared] WARN: could not create symlink $LINKPATH"

      else
        # Absent → leave absent. (No churn.)
        :
      fi
    done
  done < <(sort -u "$WS_LIST_FILE")

  rm -f "$WS_LIST_FILE" 2>/dev/null || true

  echo "  [link-shared] done: linked=$LINKED repointed=$REPOINTED backed-up=$BACKED_UP preserved=$PRESERVED workflow-agent-skipped=$SKIPPED_ANT already-ok=$NOOP"
  echo "  [link-shared] IDENTITY/SOUL/MEMORY/HEARTBEAT left as each agent's OWN files (per-agent, not shared)."
}

# ----------------------------------------------------------
# Main update logic
# ----------------------------------------------------------
main() {
  # ----------------------------------------------------------
  # Parse CLI args: --only "05,06,35" installs only those skill folders
  # (number prefix matches skill folder name prefix)
  # ----------------------------------------------------------
  ONLY_SKILLS=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --only)
        shift
        ONLY_SKILLS="${1:-}"
        ;;
      --only=*)
        ONLY_SKILLS="${1#--only=}"
        ;;
      --help|-h)
        echo "Usage: update-skills.sh [--only \"05,06,35\"]"
        echo "  --only LIST   Install only skill folders whose number prefix matches LIST (comma-separated)"
        echo "                Example: --only \"05,06,36\" installs only skills 05-ghl-setup, 06-ghl-install-pages, 36-ghl-mcp-setup"
        echo "  (no flag)     Install/update all skills"
        exit 0
        ;;
    esac
    shift || true
  done

  echo "============================================"
  echo "   OpenClaw Skills Updater (Mac)"
  echo "   Version: ${ONBOARDING_VERSION}"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE -- only [$ONLY_SKILLS]"
  fi
  echo "============================================"
  echo ""

  # Discover skills directory
  SKILLS_DIR=$(discover_skills_dir)
  export SKILLS_DIR
  echo "  📂 Skills directory: $SKILLS_DIR"

  # ----------------------------------------------------------
  # Catchup check: if last weekly cron check is older than 7 days,
  # surface a note so the user knows the Sunday cron may have missed.
  # ----------------------------------------------------------
  if [ -f "$SKILLS_DIR/.last-update-check" ]; then
    LAST_CHECK_TS=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$(cat "$SKILLS_DIR/.last-update-check")" +%s 2>/dev/null || \
                    date -d "$(cat "$SKILLS_DIR/.last-update-check")" +%s 2>/dev/null || echo 0)
    NOW_TS=$(date +%s)
    if [ "$LAST_CHECK_TS" -gt 0 ]; then
      DAYS_SINCE=$(( (NOW_TS - LAST_CHECK_TS) / 86400 ))
      if [ "$DAYS_SINCE" -gt 7 ]; then
        echo "  ℹ️  Weekly Sunday check last ran ${DAYS_SINCE} days ago -- your machine may have been asleep."
        echo "      This manual run will catch up."
      fi
    fi
  fi

  # Check for UPDATE PENDING flag
  PENDING_FILE=$(check_update_pending)
  if [ -n "$PENDING_FILE" ]; then
    echo "  ⚠️  UPDATE PENDING flag found at: $PENDING_FILE"
    echo "      Review this file before updating: cat $PENDING_FILE"
    echo ""
    read -p "Continue with update? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "  Update cancelled."
      exit 0
    fi
  fi

  # Check current version
  CURRENT_VERSION=$(get_current_version)
  if [ -n "$CURRENT_VERSION" ]; then
    echo "  Current version: $CURRENT_VERSION"
    echo "  Latest version:  $ONBOARDING_VERSION"
    if [ "$CURRENT_VERSION" = "$ONBOARDING_VERSION" ]; then
      echo ""
      read -p "Already up to date. Force re-install? (y/N) " -n 1 -r
      echo
      if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Update cancelled."
        exit 0
      fi
    fi
  else
    echo "  No previous version found -- fresh install"
  fi

  echo ""
  echo "  Downloading latest skills from GitHub..."

  # v10.15.18: clone instead of curl|unzip. Info-ZIP's `unzip` MANGLES UTF-8
  # filenames (the role-library has em-dash filenames like
  # `qc-specialist----sales.md` and `deep-research-role----openclaw-maintenance.md`)
  # and silently partial-writes them, so a zip-based update would drop or
  # corrupt those role docs. `git clone` preserves every filename byte-for-byte.
  TEMP_ZIP="/tmp/openclaw-onboarding-update.zip"
  TEMP_EXTRACT="/tmp/openclaw-onboarding-update"
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  EXTRACTED_DIR=""

  if command -v git >/dev/null 2>&1; then
    if git clone --depth 1 "https://github.com/trevorotts1/openclaw-onboarding.git" "$TEMP_EXTRACT" 2>/dev/null; then
      # HARD verify the remote is exactly the intended repo (no leftover-clone mix-up)
      _origin="$(git -C "$TEMP_EXTRACT" remote get-url origin 2>/dev/null)"
      case "$_origin" in
        https://github.com/trevorotts1/openclaw-onboarding.git|https://github.com/trevorotts1/openclaw-onboarding)
          EXTRACTED_DIR="$TEMP_EXTRACT" ;;
        *)
          echo "ERROR: cloned remote ($_origin) is NOT trevorotts1/openclaw-onboarding -- refusing to use it."
          rm -rf "$TEMP_EXTRACT"; EXTRACTED_DIR="" ;;
      esac
    fi
  fi

  # Fallback ONLY if git is unavailable or the clone failed: zip + Mac-native
  # `ditto` (NOT Info-ZIP unzip) which handles UTF-8 filenames correctly.
  if [ -z "$EXTRACTED_DIR" ]; then
    echo "  (git clone unavailable/failed -- falling back to zip + ditto)"
    curl -fSL --progress-bar "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
    rm -rf "$TEMP_EXTRACT"; mkdir -p "$TEMP_EXTRACT"
    if command -v ditto >/dev/null 2>&1; then
      ditto -x -k "$TEMP_ZIP" "$TEMP_EXTRACT" 2>/dev/null || true
    else
      unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT" 2>/dev/null || true
    fi
    if [ -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
      EXTRACTED_DIR="$TEMP_EXTRACT/openclaw-onboarding-main"
    else
      EXTRACTED_DIR=$(find "$TEMP_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1)
    fi
  fi

  if [ -z "$EXTRACTED_DIR" ] || [ ! -d "$EXTRACTED_DIR" ]; then
    echo "ERROR: Could not obtain the latest skills (git clone + zip fallback both failed)"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # v10.15.48: canonical onboarding dir for the freshly-pulled repo. Root-level
  # scripts/ (apply-fleet-standards.sh, ghl-mcp-autostart.sh, the new
  # resume-onboarding wiring) live here. Previously $ONBOARDING_DIR was
  # referenced (fleet-standards call) but never set under `set -u` -- a latent
  # bug. Define it once here so every downstream script reference resolves.
  ONBOARDING_DIR="$EXTRACTED_DIR"
  export ONBOARDING_DIR

  # v10.15.48 (FIX 1): source the onboarding STATE MACHINE + verification GATE.
  # Seed the state file with every non-archived skill at "pending" from the
  # freshly-pulled source. Statuses then advance downloaded -> wired -> qc-passed
  # as the run progresses; the "complete" report is GATED on these (below).
  if [ -f "$ONBOARDING_DIR/scripts/onboarding-state.sh" ]; then
    # shellcheck disable=SC1091
    source "$ONBOARDING_DIR/scripts/onboarding-state.sh"
    obs_seed_state "$ONBOARDING_VERSION" "$EXTRACTED_DIR" || echo "  ⚠ onboarding-state seed reported an issue (continuing)"
    # Make the gate library + helper scripts available to the running agent at
    # the canonical ~/.openclaw/scripts/ (where install.sh also lands them).
    _OC_SCRIPTS_DEST="$HOME/.openclaw/scripts"
    [ -d "/data/.openclaw" ] && _OC_SCRIPTS_DEST="/data/.openclaw/scripts"
    mkdir -p "$_OC_SCRIPTS_DEST" 2>/dev/null || true
    for _s in onboarding-state.sh ghl-mcp-autostart.sh configure-operator-telegram.sh resume-onboarding.sh apply-fleet-standards.sh diagnose-telegram-config.sh; do
      [ -f "$ONBOARDING_DIR/scripts/$_s" ] && cp -f "$ONBOARDING_DIR/scripts/$_s" "$_OC_SCRIPTS_DEST/$_s" 2>/dev/null || true
      [ -f "$_OC_SCRIPTS_DEST/$_s" ] && chmod +x "$_OC_SCRIPTS_DEST/$_s" 2>/dev/null || true
    done
  else
    echo "  ⚠ onboarding-state.sh not found in pulled repo -- honesty gate disabled for this run (older bundle?)"
  fi

  # Backup existing skills
  if [ -d "$SKILLS_DIR" ] && [ "$(ls -A "$SKILLS_DIR" 2>/dev/null)" ]; then
    BACKUP_DIR="$HOME/Downloads/openclaw-backups/skills-backup-$(date +%Y%m%d-%H%M%S)"
    echo "  Creating backup: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    cp -r "$SKILLS_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
  fi

  # Ensure skills directory exists
  mkdir -p "$SKILLS_DIR"

  # Copy new skills
  echo "  Installing skills to $SKILLS_DIR..."
  NEW_SKILLS_CSV=""
  SKIPPED_COUNT=0
  for SKILL_DIR in "$EXTRACTED_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")

    # Skip archived skills
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # --only filter: if ONLY_SKILLS is set, install only matching prefixes
    if [ -n "$ONLY_SKILLS" ]; then
      SKILL_PREFIX=$(echo "$SKILL_NAME" | cut -d'-' -f1)
      MATCH="false"
      OIFS=$IFS; IFS=','
      for want in $ONLY_SKILLS; do
        want_trimmed=$(echo "$want" | tr -d '[:space:]')
        if [ "$SKILL_PREFIX" = "$want_trimmed" ]; then
          MATCH="true"
          break
        fi
      done
      IFS=$OIFS
      if [ "$MATCH" != "true" ]; then
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        continue
      fi
    fi

    # Check if this is a NEW skill (doesn't exist in current install)
    if [ ! -d "$SKILLS_DIR/$SKILL_NAME" ]; then
      # Track for flag + Telegram
      if [ -z "$NEW_SKILLS_CSV" ]; then
        NEW_SKILLS_CSV="$SKILL_NAME"
      else
        NEW_SKILLS_CSV="$NEW_SKILLS_CSV, $SKILL_NAME"
      fi
      echo ""
      echo "  🆕 NEW SKILL DETECTED: $SKILL_NAME"
      echo "  ============================================"
      echo "  This skill requires ACTIVATION after install."
      echo "  The agent MUST follow these steps:"
      echo ""
      echo "  a. READ all files (Teach Yourself Protocol)"
      echo "     → SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md"
      echo "     → Plus any references/*.md files"
      echo ""
      echo "  b. CHECK prerequisites, search .env files"
      echo "     → Verify API keys, credentials, software"
      echo "     → Check ~/.openclaw/skills/ for dependencies"
      echo ""
      echo "  c. EXECUTE setup (different from reading!)"
      echo "     → Follow INSTALL.md activation steps"
      echo "     → Copy scripts, create files, run commands"
      echo "     → 'Teach Yourself' means READ. 'Activate' means EXECUTE."
      echo ""
      echo "  d. APPLY CORE_UPDATES.md surgically"
      echo "     → Add to AGENTS.md, TOOLS.md, MEMORY.md"
      echo "     → Update HEARTBEAT.md if needed"
      echo ""
      echo "  e. RUN QC.md checks"
      echo "     → Verify all components work"
      echo "     → Test API connections"
      echo ""
      echo "  f. TELL client what was set up"
      echo "     → List activated features"
      echo "     → Note any pending items"
      echo ""
      echo "  ============================================"
    fi

    # Remove old version if exists
    rm -rf "$SKILLS_DIR/$SKILL_NAME"

    # Copy new version.
    # IMPORTANT: strip the trailing slash from SKILL_DIR before passing to cp.
    # The glob pattern [0-9]*/ always appends a trailing slash.
    # `cp -r "path/01-skill/" dest/` copies the CONTENTS of 01-skill/ flat
    # into dest/ (the dir itself is not created) -- this is the root cause of
    # the "132 loose files dumped into ~/.openclaw/skills/" flatten bug.
    # `cp -r "path/01-skill" dest/` (no trailing slash) copies the dir as a
    # named subdirectory, producing dest/01-skill/ as intended.
    cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"
    echo "    Updated: $SKILL_NAME"
    # FIX 1: state transition -- files are on disk = DOWNLOADED (NOT installed).
    command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "downloaded"
  done

  # ----------------------------------------------------------
  # v10.15.47: WIRING PHASE -- per-skill executed steps (not prose).
  # For every installed skill folder, this phase:
  #   1. Runs the skill's own installer (wire.sh > install.sh > setup-*.sh) if present, idempotent.
  #   2. Idempotently merges CORE_UPDATES.md into workspace AGENTS/TOOLS/MEMORY/SOUL files.
  #   3. Installs OS prereqs (imagemagick/ffmpeg) via brew (Mac) idempotently.
  #   4. Wires skill 36's GHL MCP under nested mcp.servers via `openclaw mcp set`.
  #
  # State guard: each skill writes a sentinel file $SKILLS_DIR/<skill>/.wired-<version>
  # so the loop is safe to re-run -- it skips already-wired skills.
  #
  # Scope: additive only. Never edits IDENTITY.md, never rebuilds workforce,
  # never clobbers existing AGENTS.md sections -- only appends new ones.
  # ----------------------------------------------------------

  # Resolve workspace directory (mirrors write_update_pending_flag)
  WIRE_WORKSPACE_DIR="$HOME/clawd"
  [ ! -d "$WIRE_WORKSPACE_DIR" ] && WIRE_WORKSPACE_DIR="$HOME/.openclaw/workspace"
  mkdir -p "$WIRE_WORKSPACE_DIR"

  # Brew path (Mac only; VPS branch kept out, VPS uses update-skills-vps.sh)
  BREW_CMD="$(command -v brew 2>/dev/null || echo '')"

  # ---- Helper: idempotent CORE_UPDATES.md merger ----
  wire_core_updates() {
    local SKILL_FOLDER="$1"   # e.g. "36-ghl-mcp-setup"
    local CU_FILE="$SKILLS_DIR/$SKILL_FOLDER/CORE_UPDATES.md"
    [ -f "$CU_FILE" ] || return 0

    # Map section headers to workspace target files
    local AGENTS_FILE="$WIRE_WORKSPACE_DIR/AGENTS.md"
    local TOOLS_FILE="$WIRE_WORKSPACE_DIR/TOOLS.md"
    local MEMORY_FILE="$WIRE_WORKSPACE_DIR/MEMORY.md"
    local SOUL_FILE="$WIRE_WORKSPACE_DIR/SOUL.md"
    touch "$AGENTS_FILE" "$TOOLS_FILE" "$MEMORY_FILE" "$SOUL_FILE" 2>/dev/null || true

    # Sentinel: skip if this skill's core updates are already merged
    local SENTINEL="<!-- skill:${SKILL_FOLDER}:core-update-applied -->"
    if grep -qF "$SENTINEL" "$AGENTS_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$TOOLS_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$MEMORY_FILE" 2>/dev/null; then
      return 0
    fi

    # Parse CORE_UPDATES.md: extract each labeled section and append to the right file.
    # Sections are delimited by lines matching: ## <TARGET>.md -- UPDATE REQUIRED
    # or: ## <TARGET>.md -- NO UPDATE NEEDED  (skip those).
    # We use python3 (always present on Mac) for safe multi-line extraction.
    python3 - "$CU_FILE" "$AGENTS_FILE" "$TOOLS_FILE" "$MEMORY_FILE" "$SOUL_FILE" "$SENTINEL" <<'PYEOF'
import sys, re

cu_path, agents_f, tools_f, memory_f, soul_f, sentinel = sys.argv[1:]

target_map = {
    'agents': agents_f,
    'tools':  tools_f,
    'memory': memory_f,
    'soul':   soul_f,
}

try:
    text = open(cu_path, encoding='utf-8', errors='replace').read()
except Exception:
    sys.exit(0)

# Split on section headers like: ## AGENTS.md -- UPDATE REQUIRED
# or ## AGENTS.md -- NO UPDATE NEEDED
header_re = re.compile(
    r'^##\s+(AGENTS|TOOLS|MEMORY|SOUL)\.md\s*[--–-]+\s*(.*?)$',
    re.IGNORECASE | re.MULTILINE
)

sections = list(header_re.finditer(text))
if not sections:
    sys.exit(0)

for i, m in enumerate(sections):
    key = m.group(1).lower()
    directive = m.group(2).strip().lower()
    if 'no update' in directive:
        continue
    target_file = target_map.get(key)
    if not target_file:
        continue

    # Content is between this header and the next (or EOF)
    start = m.end()
    end = sections[i+1].start() if i+1 < len(sections) else len(text)
    block = text[start:end].strip()
    if not block:
        continue

    # Check sentinel in target file before appending
    try:
        existing = open(target_file, encoding='utf-8', errors='replace').read()
    except Exception:
        existing = ''
    if sentinel in existing:
        continue

    # Append block + sentinel
    with open(target_file, 'a', encoding='utf-8') as fh:
        fh.write('\n\n')
        fh.write(block)
        fh.write('\n')

# Write sentinel to AGENTS.md (primary guard file)
try:
    existing = open(agents_f, encoding='utf-8', errors='replace').read()
except Exception:
    existing = ''
if sentinel not in existing:
    with open(agents_f, 'a', encoding='utf-8') as fh:
        fh.write('\n' + sentinel + '\n')

PYEOF
    echo "    Wired CORE_UPDATES.md: $SKILL_FOLDER"
  }

  # ---- Helper: install OS prereqs for a skill (idempotent) ----
  wire_prereqs() {
    local SKILL_FOLDER="$1"
    # Skills 25/26/27/28 need ffmpeg + imagemagick; 16 needs nothing extra.
    # We detect by folder prefix; adding explicit cases is safer than parsing INSTALL.md.
    local NEED_FFMPEG=0
    local NEED_IMAGEMAGICK=0
    case "$SKILL_FOLDER" in
      25-video-creator|26-caption-creator|27-video-editor|28-cinematic-forge)
        NEED_FFMPEG=1; NEED_IMAGEMAGICK=1 ;;
    esac

    [ "$NEED_FFMPEG" -eq 0 ] && [ "$NEED_IMAGEMAGICK" -eq 0 ] && return 0
    [ -z "$BREW_CMD" ] && { echo "    (brew not found -- skipping prereqs for $SKILL_FOLDER)"; return 0; }

    if [ "$NEED_FFMPEG" -eq 1 ]; then
      if command -v ffmpeg >/dev/null 2>&1; then
        echo "    ffmpeg: already installed"
      else
        echo "    Installing ffmpeg via brew..."
        "$BREW_CMD" install ffmpeg >> "$LOG_FILE" 2>&1 && echo "    ffmpeg: installed" || echo "    ffmpeg: install failed (see $LOG_FILE)"
      fi
    fi

    if [ "$NEED_IMAGEMAGICK" -eq 1 ]; then
      if command -v convert >/dev/null 2>&1 || command -v magick >/dev/null 2>&1; then
        echo "    imagemagick: already installed"
      else
        echo "    Installing imagemagick via brew..."
        "$BREW_CMD" install imagemagick >> "$LOG_FILE" 2>&1 && echo "    imagemagick: installed" || echo "    imagemagick: install failed (see $LOG_FILE)"
      fi
    fi
  }

  # ---- Helper: wire skill 36 GHL MCP under nested mcp.servers (idempotent) ----
  wire_ghl_mcp() {
    local SKILL_FOLDER="$1"
    [ "$SKILL_FOLDER" = "36-ghl-mcp-setup" ] || return 0

    if ! command -v openclaw >/dev/null 2>&1; then
      echo "    (openclaw CLI not found -- skipping GHL MCP registration)"
      return 0
    fi

    # Check if ghl-mcp is already registered under nested mcp.servers
    local OCJSON="$HOME/.openclaw/openclaw.json"
    if [ -f "$OCJSON" ] && python3 -c "
import json, sys
try:
    cfg = json.load(open('$OCJSON'))
    servers = cfg.get('mcp', {}).get('servers', {})
    if 'ghl-mcp' in servers or 'ghl-community-mcp' in servers:
        sys.exit(0)
    sys.exit(1)
except:
    sys.exit(1)
" 2>/dev/null; then
      echo "    GHL MCP: already registered under mcp.servers"
      return 0
    fi

    # Read GHL MCP URL from skill's INSTALL.md or default to the community server
    # The canonical CLI path per audit finding (d): openclaw mcp set
    local GHL_MCP_PORT=8765
    local GHL_MCP_INSTALL_MD="$SKILLS_DIR/36-ghl-mcp-setup/INSTALL.md"
    if [ -f "$GHL_MCP_INSTALL_MD" ]; then
      local DETECTED_PORT
      DETECTED_PORT=$(grep -oE 'localhost:[0-9]+' "$GHL_MCP_INSTALL_MD" 2>/dev/null | head -1 | cut -d: -f2)
      [ -n "$DETECTED_PORT" ] && GHL_MCP_PORT="$DETECTED_PORT"
    fi

    echo "    Registering GHL community MCP under mcp.servers (port $GHL_MCP_PORT)..."
    if openclaw mcp set ghl-community-mcp "{\"type\":\"streamable-http\",\"url\":\"http://localhost:${GHL_MCP_PORT}/mcp\"}" >> "$LOG_FILE" 2>&1; then
      echo "    GHL MCP: registered under mcp.servers (ghl-community-mcp → localhost:${GHL_MCP_PORT})"
    else
      echo "    GHL MCP: registration attempt completed (see $LOG_FILE for details)"
    fi

    # FIX 3 (v10.15.48): registration alone NEVER starts the local server, so
    # the GHL tools don't resolve. Run the EXECUTED autostart (launchd KeepAlive
    # on :8765 + healthcheck + auto-restart). Idempotent -- no-op if already
    # healthy + registered; honest SKIP line if GHL creds are absent.
    # BUG FIX (v10.15.49): run NON-BLOCKING so the wiring loop + .onboarding-version
    # stamp always complete. macOS has no `timeout`, so backgrounding is the safe
    # cross-platform fix. The MCP still starts; the updater no longer waits on it.
    local AUTOSTART="$ONBOARDING_DIR/scripts/ghl-mcp-autostart.sh"
    if [ -x "$AUTOSTART" ]; then
      echo "    Starting GHL MCP server in background (launchd :${GHL_MCP_PORT}) -- log: /tmp/ghl-mcp-autostart.log"
      ( GHL_MCP_PORT="$GHL_MCP_PORT" bash "$AUTOSTART" >/tmp/ghl-mcp-autostart.log 2>&1 & )
    else
      echo "    (ghl-mcp-autostart.sh not found at $AUTOSTART -- server NOT started; GHL tools will not resolve until it is run)"
    fi
  }

  # ---- Main wiring loop ----
  echo ""
  echo "  Wiring installed skills (CORE_UPDATES, prereqs, MCP registration)..."
  WIRED_COUNT=0
  SKIPPED_WIRED_COUNT=0

  for SKILL_DIR in "$SKILLS_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # Per-skill idempotency sentinel
    WIRED_SENTINEL="$SKILL_DIR/.wired-${ONBOARDING_VERSION}"
    if [ -f "$WIRED_SENTINEL" ]; then
      SKIPPED_WIRED_COUNT=$((SKIPPED_WIRED_COUNT + 1))
      continue
    fi

    # Step 1: Run the skill's own executable installer if present
    # Priority: wire.sh > install.sh > setup-*.sh (first match)
    SKILL_INSTALLER=""
    for _candidate in "$SKILL_DIR/wire.sh" "$SKILL_DIR/install.sh" "$SKILL_DIR/scripts/install.sh"; do
      if [ -x "$_candidate" ]; then
        SKILL_INSTALLER="$_candidate"
        break
      fi
    done
    # Also check for setup-*.sh pattern
    if [ -z "$SKILL_INSTALLER" ]; then
      for _candidate in "$SKILL_DIR"/setup-*.sh "$SKILL_DIR"/scripts/setup-*.sh; do
        if [ -x "$_candidate" ]; then
          SKILL_INSTALLER="$_candidate"
          break
        fi
      done
    fi

    if [ -n "$SKILL_INSTALLER" ]; then
      echo "    Running installer: $(basename "$SKILL_INSTALLER") for $SKILL_NAME..."
      if bash "$SKILL_INSTALLER" --idempotent >> "$LOG_FILE" 2>&1; then
        echo "    Installer OK: $SKILL_NAME"
      else
        echo "    Installer reported warnings for $SKILL_NAME (see $LOG_FILE) -- continuing"
      fi
    fi

    # Step 2: Idempotently merge CORE_UPDATES.md into workspace files
    wire_core_updates "$SKILL_NAME"

    # Step 3: Install OS prereqs (ffmpeg/imagemagick for video skills)
    wire_prereqs "$SKILL_NAME"

    # Step 4: Wire GHL MCP (skill 36 only)
    wire_ghl_mcp "$SKILL_NAME"

    # Step 5 (v12.0.0): Per-skill prerequisite check -- NOT sentinel-gated.
    # Runs on every wiring pass so a prereq satisfied between runs clears on
    # the next update. Exit 2 = installed-with-missing-prereqs (note + continue).
    # Exit 3 = malformed PREREQS.json (warn + continue). Read-only; self-records.
    PREREQ_CHECKER_UPDATE="$SKILLS_DIR/shared-utils/check-skill-prereqs.sh"
    if [[ -x "$PREREQ_CHECKER_UPDATE" && -f "$SKILL_DIR/PREREQS.json" ]]; then
      PREREQ_RC_UPDATE=0
      bash "$PREREQ_CHECKER_UPDATE" "$SKILL_DIR" || PREREQ_RC_UPDATE=$?
      if [[ $PREREQ_RC_UPDATE -eq 2 ]]; then
        echo "    [prereq] $SKILL_NAME: installed with missing prerequisites"
      elif [[ $PREREQ_RC_UPDATE -eq 3 ]]; then
        echo "    [prereq] $SKILL_NAME: WARN malformed PREREQS.json (skipped)"
      fi
    fi

    # Mark skill as wired for this version
    touch "$WIRED_SENTINEL" 2>/dev/null || true
    # FIX 1: state transition -- installer + CORE_UPDATES merge ran = WIRED
    # (still NOT "installed" until the verification gate passes below).
    command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "wired"
    WIRED_COUNT=$((WIRED_COUNT + 1))
  done

  echo "  Wiring complete: $WIRED_COUNT skill(s) wired, $SKIPPED_WIRED_COUNT already wired (idempotent skip)"

  # ----------------------------------------------------------
  # v10.15.42: Run migrate-existing-workforce.sh so copied skills
  # actually install into the client's live department tree.
  # This script is idempotent and additive -- it never deletes or
  # overwrites existing departments, only fills gaps.
  # ----------------------------------------------------------
  MIGRATE_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh"
  if [ -x "$MIGRATE_SCRIPT" ]; then
    echo ""
    echo "  Running workforce migration (installs copied skills into department tree)..."
    if bash "$MIGRATE_SCRIPT" "$(hostname)" --apply >> "$LOG_FILE" 2>&1; then
      echo "  migrate-existing-workforce.sh: OK"
    else
      echo "  migrate-existing-workforce.sh: completed with warnings (see $LOG_FILE)"
    fi
  else
    echo "  (migrate-existing-workforce.sh not found or not executable -- skipping)"
  fi

  # ----------------------------------------------------------
  # v10.15.51: SHARED CORE FILE UNIFICATION (Zero-Human-Workforce file model).
  # AFTER skills + workspaces + CORE_UPDATES wiring + workforce migration, every
  # agent/sub-agent on THIS box shares the box's ONE canonical AGENTS.md /
  # TOOLS.md / USER.md via symlink. Per-agent IDENTITY/SOUL/MEMORY/HEARTBEAT stay
  # each agent's own. Nested workflow agents exempt. Idempotent. Reads THIS box's
  # openclaw.json only (co-mingling guard) -- never a foreign/hardcoded target.
  # ----------------------------------------------------------
  echo ""
  echo "  Unifying shared core files (AGENTS/TOOLS/USER symlinked to this box's canonical)..."
  link_shared_core_files || echo "  ⚠ link_shared_core_files reported warnings (update continues)"

  # Write version file to active dir (the canonical location)
  echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"

  # Sync version marker to legacy locations if they exist, so get_current_version
  # always reads the same value regardless of which path it finds first.
  # This prevents the stale-legacy-marker false-positive on re-runs (Bug B).
  for _LEGACY_MARKER in \
      "$HOME/Downloads/openclaw-master-files/.onboarding-version" \
      "$HOME/.openclaw/onboarding/.onboarding-version"; do
    if [ -f "$_LEGACY_MARKER" ]; then
      echo "$ONBOARDING_VERSION" > "$_LEGACY_MARKER" 2>/dev/null || true
    fi
  done

  # ----------------------------------------------------------
  # VERIFICATION: confirm the active dir was actually updated.
  # If SKILLS_DIR's .onboarding-version does not match what we
  # just wrote, something redirected writes away from the active
  # dir -- fail loudly instead of reporting false success.
  # ----------------------------------------------------------
  VERIFY_VER=$(cat "$SKILLS_DIR/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
  if [ "$VERIFY_VER" != "$ONBOARDING_VERSION" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  FAILURE: active skills dir was NOT updated!"
    echo "  Expected version : $ONBOARDING_VERSION"
    echo "  Found version    : ${VERIFY_VER:-<missing>}"
    echo "  Active dir       : $SKILLS_DIR"
    echo "  The running agent is still on the OLD skills."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi
  VERIFY_SKILL_COUNT=$(ls -d "$SKILLS_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
  if [ "$VERIFY_SKILL_COUNT" -eq 0 ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  FAILURE: no skill folders found in active dir after update!"
    echo "  Active dir : $SKILLS_DIR"
    echo "  The running agent is still on the OLD skills."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Cleanup
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"

  # ----------------------------------------------------------
  # FIX 1: VERIFICATION GATE -- run the gate on EVERY non-archived skill.
  # A skill counts INSTALLED only if (a) openclaw skills info shows it,
  # (b) its CORE_UPDATES sentinel is present (if it ships one), and (c) its
  # qc-*.sh exits 0 (if it ships one). We DO NOT claim "installed/onboarded"
  # for un-registered skills. The "complete" Telegram below is CONDITIONAL on
  # this gate. ONBOARDING_GATE_OK / _SUMMARY drive the honest report.
  # ----------------------------------------------------------
  ONBOARDING_GATE_OK="unknown"
  ONBOARDING_GATE_SUMMARY=""
  if command -v obs_verify_skill >/dev/null 2>&1; then
    echo ""
    echo "  Running the per-skill VERIFICATION GATE (skills info + CORE_UPDATES sentinel + qc-*.sh)..."
    for _gskill in "$SKILLS_DIR"/[0-9]*/; do
      [ -d "$_gskill" ] || continue
      _gname="$(basename "$_gskill")"
      case "$_gname" in *ARCHIVED*) continue ;; esac
      if _greason="$(obs_verify_skill "$_gname" "$SKILLS_DIR")"; then
        echo "    ✓ verified-installed: $_gname"
      else
        echo "    ✗ NOT verified: $_gname -- ${_greason}"
      fi
    done
    ONBOARDING_GATE_SUMMARY="$(obs_gate_summary "$SKILLS_DIR" 2>/dev/null | grep '^GATE-HUMAN:' | sed 's/^GATE-HUMAN: //')"
    if obs_gate_summary "$SKILLS_DIR" >/dev/null 2>&1; then
      ONBOARDING_GATE_OK="yes"
    else
      ONBOARDING_GATE_OK="no"
    fi
  else
    echo "  ⚠ verification gate unavailable (onboarding-state.sh not sourced) -- cannot honestly verify; will report file-sync only."
  fi

  echo ""
  echo "============================================"
  if [ "$ONBOARDING_GATE_OK" = "yes" ]; then
    echo "   Skills updated AND verified-installed."
  elif [ "$ONBOARDING_GATE_OK" = "no" ]; then
    echo "   Skills FILE-SYNCED to disk -- NOT all verified-installed yet."
    echo "   ${ONBOARDING_GATE_SUMMARY:-(gate summary unavailable)}"
    echo "   (The onboarding-resume cron will re-fire wiring + QC until all pass.)"
  else
    echo "   Skills file-synced to disk (verification gate did not run)."
  fi
  echo "   Version: $ONBOARDING_VERSION"
  echo "   Location: $SKILLS_DIR"
  echo "   Files on disk: $VERIFY_SKILL_COUNT skill folders confirmed in active dir"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE -- only [$ONLY_SKILLS]"
    echo "   Skipped: $SKIPPED_COUNT other skills (not in --only list)"
  fi
  echo "============================================"

  # Mark the check timestamp so the catchup logic in future runs is accurate
  date -u +%Y-%m-%dT%H:%M:%SZ > "$SKILLS_DIR/.last-update-check" 2>/dev/null || true

  # ----------------------------------------------------------
  # Ensure the Sunday weekly update-check cron exists (idempotent)
  # Existing clients on pre-v9.2.0 won't have it; running the updater
  # backfills it.
  # ----------------------------------------------------------
  if command -v openclaw >/dev/null 2>&1; then
    if openclaw cron list 2>/dev/null | grep -qi "weekly-onboarding-update"; then
      echo "  ✓ Sunday weekly update-check cron already installed"
    else
      OCJSON="$HOME/.openclaw/openclaw.json"
      [ -d "/data/.openclaw" ] && OCJSON="/data/.openclaw/openclaw.json"
      TG_TARGET=""
      if [ -f "$OCJSON" ]; then
        TG_TARGET=$(python3 -c "
import json
try:
    cfg=json.load(open('$OCJSON'))
    allow=cfg.get('channels',{}).get('telegram',{}).get('allowFrom',[])
    if allow: print(allow[0])
except: pass
" 2>/dev/null)
      fi
      if [ -n "$TG_TARGET" ]; then
        PROMPT_TMP="/tmp/openclaw-cron-prompt-$$.txt"
        REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"
        # Unified repo: same URL for both Mac and VPS platforms
        if curl -fsSL --max-time 15 "${REPO_URL}/cron-prompt.txt" -o "$PROMPT_TMP" 2>/dev/null && [ -s "$PROMPT_TMP" ]; then
          PROMPT_CONTENT=$(cat "$PROMPT_TMP")
          if openclaw cron create \
              --name "weekly-onboarding-update" \
              --description "Sunday 2am ET -- check for OpenClaw onboarding + command-center updates and ask client permission before applying anything." \
              --cron "0 3 * * 0" \
              --tz "America/New_York" \
              --exact \
              --session isolated \
              --announce \
              --channel telegram \
              --to "$TG_TARGET" \
              --thinking high \
              --timeout-seconds 7200 \
              --message "$PROMPT_CONTENT" >/dev/null 2>&1; then
            echo "  ✓ Sunday weekly update-check cron installed (Sundays 2am ET → telegram $TG_TARGET)"
          else
            echo "  ⚠ Cron install failed -- agent can retry manually"
          fi
          rm -f "$PROMPT_TMP"
        else
          echo "  ⚠ Could not fetch cron-prompt.txt -- agent can install cron manually later"
        fi
      else
        echo "  ⚠ No telegram target configured -- skipping cron install. Configure Telegram first then re-run."
      fi
    fi
  fi

  # ----------------------------------------------------------
  # Fleet standards: ensure sub-agents fully permitted + Telegram media 50MB
  # (idempotent -- applied on every update, no-op if already canonical)
  # ----------------------------------------------------------
  echo ""
  echo "  Applying fleet standards (sub-agents fully permitted, Telegram media 50MB)..."
  if [ -f "$ONBOARDING_DIR/scripts/apply-fleet-standards.sh" ]; then
    bash "$ONBOARDING_DIR/scripts/apply-fleet-standards.sh" >/dev/null 2>&1 && echo "  ✓ Fleet standards applied" || echo "  ⚠ Fleet standards application reported errors (update continues)"
  else
    echo "  ⚠ Fleet standards script not found"
  fi

  # ----------------------------------------------------------
  # v10.15.4: Post-pull qc-completeness check. Read-only. Runs against the live
  # workforce after every successful skill pull. The script self-Telegrams the
  # operator on != PASS, so we just append the human-readable STATUS line to
  # the existing "update complete" Telegram for visibility.
  # ----------------------------------------------------------
  QC_COMPLETENESS_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/qc-completeness.sh"
  QC_STATUS_LINE=""
  QC_COMPLETENESS_RC=0   # FIX 1: HONOR this exit code (was ignored). 0=PASS, 2=PARTIAL, 3=FAIL, 4=NO_WORKFORCE
  if [ -x "$QC_COMPLETENESS_SCRIPT" ]; then
    echo ""
    echo "  Running qc-completeness.sh against live workforce..."
    QC_OUTPUT="$(bash "$QC_COMPLETENESS_SCRIPT" 2>&1)" || QC_COMPLETENESS_RC=$?
    QC_STATUS_LINE="$(printf '%s\n' "$QC_OUTPUT" | grep -E '^STATUS:' | tail -1)"
    echo "  ${QC_STATUS_LINE:-qc-completeness ran (no STATUS line captured)} (exit $QC_COMPLETENESS_RC)"
  fi

  # ----------------------------------------------------------
  # Post-update: write UPDATE PENDING flag + Telegram + backup block
  # ----------------------------------------------------------
  echo ""
  echo "  Writing UPDATE PENDING flag for agent activation..."
  write_update_pending_flag "$ONBOARDING_VERSION" "$NEW_SKILLS_CSV"

  echo "  Sending Telegram notification..."
  # ----------------------------------------------------------
  # FIX 1: HONEST REPORTING CONTRACT. The headline is CONDITIONAL on the
  # verification gate (ONBOARDING_GATE_OK) AND the workforce qc-completeness
  # exit code (QC_COMPLETENESS_RC, previously ignored). We NEVER say
  # "complete/installed/onboarded" unless BOTH gates pass. Otherwise we report
  # the truth: how many skills are verified vs. not, and that resume will retry.
  # ----------------------------------------------------------
  _TG_HEADLINE=""
  if [ "$ONBOARDING_GATE_OK" = "yes" ] && { [ "${QC_COMPLETENESS_RC:-0}" -eq 0 ] || [ "${QC_COMPLETENESS_RC:-0}" -eq 4 ]; }; then
    # Gate passed (qc=PASS, or NO_WORKFORCE which is not an install failure).
    _TG_HEADLINE="✅ OpenClaw skill update ${ONBOARDING_VERSION} verified-installed.

${ONBOARDING_GATE_SUMMARY:-all skills verified}."
  else
    # Honest partial. NEVER claim done.
    _TG_HEADLINE="⏳ OpenClaw skill update ${ONBOARDING_VERSION}: files synced, NOT all verified yet.

${ONBOARDING_GATE_SUMMARY:-verification gate did not produce a summary}.

The onboarding-resume cron will keep re-firing wiring + QC until every skill passes (it does NOT stop on a self-declared 'done')."
  fi

  send_telegram_progress "${_TG_HEADLINE}

New skills (need activation): ${NEW_SKILLS_CSV:-none -- updates only}.

Workforce QC: ${QC_STATUS_LINE:-not run} (exit ${QC_COMPLETENESS_RC:-?})

Paste this to your agent:

▶ \"I just ran update-skills.sh. There is an UPDATE PENDING flag at the top of my AGENTS.md describing what changed. Check .onboarding-state.json and run the verification gate (scripts/onboarding-state.sh). Activate + QC every skill that is not yet qc-passed. Do NOT report done until the gate passes. Send me a summary when the gate is green.\"

(If you didn't get THIS Telegram note, the same instructions are also printed in your Terminal.)"

  case "$TELEGRAM_LAST_RESULT" in
    sent:*)              echo "  ✓ Telegram sent to ${TELEGRAM_LAST_RESULT#sent:}" ;;
    no-openclaw-cli)     echo "  ⚠ Telegram skipped -- openclaw CLI not on PATH" ;;
    no-telegram-target)  echo "  ⚠ Telegram skipped -- no telegram.allowFrom configured in openclaw.json" ;;
    failed:*)            echo "  ⚠ Telegram FAILED -- see $LOG_FILE (using backup block below)" ;;
  esac

  # Always print the backup block so client is never stranded
  cat <<'BACKUP_BLOCK'

╔════════════════════════════════════════════════════════════════════╗
║   BACKUP -- IF YOU DID NOT GET A TELEGRAM NOTE                      ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   Open whatever you use to talk to your OpenClaw agent (Telegram,  ║
║   web UI, terminal chat -- whatever you have set up).               ║
║                                                                    ║
║   Paste this EXACT message to your agent (copy between the         ║
║   >>> and <<< markers):                                            ║
║                                                                    ║
║   >>>                                                              ║
║   I just ran update-skills.sh. There is an UPDATE PENDING flag     ║
║   at the top of my AGENTS.md describing what changed. Please       ║
║   follow the activation steps for any new skills listed in the     ║
║   flag. Run QC after each one. Send me a summary when complete.    ║
║   <<<                                                              ║
║                                                                    ║
║   Your agent will read the flag and walk through the activation    ║
║   for you. You don't need to type any other commands.              ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

BACKUP_BLOCK
}

main "$@"
