#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  OpenClaw Skills Updater — Mac Version
#  Updates skills from GitHub to ~/Downloads/openclaw-master-files/
# ============================================================

ONBOARDING_VERSION="v10.15.47"

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

  local WORKSPACE_DIR="$HOME/clawd"
  [ ! -d "$WORKSPACE_DIR" ] && WORKSPACE_DIR="$HOME/.openclaw/workspace"
  mkdir -p "$WORKSPACE_DIR"
  local AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"

  touch "$AGENTS_FILE"
  grep -v "UPDATE PENDING\|ONBOARDING PENDING" "$AGENTS_FILE" > "$AGENTS_FILE.tmp" 2>/dev/null || true
  mv "$AGENTS_FILE.tmp" "$AGENTS_FILE" 2>/dev/null || true

  local DATE_STAMP
  DATE_STAMP=$(date +%Y-%m-%d)

  cat >> "$AGENTS_FILE" <<FLAGCONTENT

## 🔴🔴🔴 UPDATE PENDING — SKILL UPDATE TO ${version}

**EXECUTION MODE: DO NOT ASK PERMISSION. EXECUTE IMMEDIATELY.**

A skill update was applied via update-skills.sh on ${DATE_STAMP}. Process the activation steps now.

### What changed in this update
- Onboarding version: ${version}
- New skills installed (require ACTIVATION): ${new_skills:-none — updates only}

### How to process each NEW skill (only NEW ones, updates are already in place)

For each new skill folder under \`~/.openclaw/skills/\`:
1. READ all files (Teach Yourself Protocol): SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md, plus any \`references/*.md\` files
2. CHECK prerequisites and search ALL standard credential locations (canonical: \`~/.openclaw/secrets/.env\` on Mac, \`/data/.openclaw/secrets/.env\` on VPS, plus \`openclaw.json\` env.vars). Skip asking the owner if values already exist.
3. EXECUTE the activation steps in INSTALL.md (read ≠ execute)
4. APPLY CORE_UPDATES.md surgically — add to AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md only the sections explicitly labeled in that file
5. RUN the bundled QC checks; do not declare done until QC reaches a pass score (skills with a \`qc-*.sh\` script must exit 0)
6. REPORT to owner what was activated and any items pending owner input

### Discipline (binding)
- Skills 22-23: MAIN ORCHESTRATOR ONLY, never delegate
- Tier order in any tiered skill (e.g. skill 36 GHL MCP): try Tier N before Tier N+1, no skipping
- Disclosure headers (e.g. \`[GHL tier used: N — tool_name]\`) required per any skill's SOUL-level rules
- No destructive shortcuts: no \`--force\`, no \`--no-verify\`, no \`--break-system-packages\` unless explicitly instructed

### When activation is complete
- Remove this entire UPDATE PENDING section from AGENTS.md
- Add to MEMORY.md under "## System Updates":
  "${version} update applied on ${DATE_STAMP}. New skills activated: ${new_skills:-none}."

FLAGCONTENT
  echo "  ✓ UPDATE PENDING flag written to $AGENTS_FILE"

  # Seed Core.md terminology into MEMORY.md (idempotent)
  local MEMORY_FILE="$WORKSPACE_DIR/MEMORY.md"
  touch "$MEMORY_FILE"
  if ! grep -q "## Terminology — Core.md Files" "$MEMORY_FILE" 2>/dev/null; then
    cat >> "$MEMORY_FILE" << 'COREMDEOF'

## Terminology — Core.md Files

When the owner says **"Core.md files"** they mean the OpenClaw bootstrap files loaded every session — not a literal file called `core.md`. The Core.md files are:

- **IDENTITY.md** — the role the agent is playing. It contains the **experiences and the skills they need to embody** that role. Not just surface metadata (name / vibe / emoji) — the lived background and capability set of the character being played.
- **SOUL.md** — the **personality** of the agent, its **true mission**, its **beliefs**, its **rules**, its **goals**, its **belief systems**, its **principles**. Who the agent IS, not who they are playing. First file injected each session.
- **AGENTS.md** — operating procedures, protocols, workflows, memory rules. *What the agent does and how*
- **USER.md** — the human being helped (name, timezone, preferences, communication style)
- **TOOLS.md** — local tool notes and conventions (camera names, SSH aliases, environment-specific specifics) — NOT a permissions registry
- **MEMORY.md** — curated long-term durable facts, decisions, preferences. Loaded in main private sessions; paired with daily logs at `memory/YYYY-MM-DD.md`

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
# SKILLS DIRECTORY SECTION — Active-dir-first detection
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
# Discover skills directory — active dir first
# ----------------------------------------------------------
discover_skills_dir() {
  # Detect platform: VPS has /data, Mac does not
  if [ -d /data ]; then
    # VPS (Hostinger Docker) — active path is /data/.openclaw/skills
    local ACTIVE_DIR="/data/.openclaw/skills"
  else
    # Mac — active path is ~/.openclaw/skills
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

  # Active dir exists but is empty (first-install into it) — still prefer it
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
# UPDATE PENDING flag handling — search correct locations
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
# Check .onboarding-version — search multiple paths
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
    echo "   Mode: SELECTIVE — only [$ONLY_SKILLS]"
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
        echo "  ℹ️  Weekly Sunday check last ran ${DAYS_SINCE} days ago — your machine may have been asleep."
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
    echo "  No previous version found — fresh install"
  fi

  echo ""
  echo "  Downloading latest skills from GitHub..."

  # v10.15.18: clone instead of curl|unzip. Info-ZIP's `unzip` MANGLES UTF-8
  # filenames (the role-library has em-dash filenames like
  # `qc-specialist-—-sales.md` and `deep-research-role-—-openclaw-maintenance.md`)
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
          echo "ERROR: cloned remote ($_origin) is NOT trevorotts1/openclaw-onboarding — refusing to use it."
          rm -rf "$TEMP_EXTRACT"; EXTRACTED_DIR="" ;;
      esac
    fi
  fi

  # Fallback ONLY if git is unavailable or the clone failed: zip + Mac-native
  # `ditto` (NOT Info-ZIP unzip) which handles UTF-8 filenames correctly.
  if [ -z "$EXTRACTED_DIR" ]; then
    echo "  (git clone unavailable/failed — falling back to zip + ditto)"
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
    # into dest/ (the dir itself is not created) — this is the root cause of
    # the "132 loose files dumped into ~/.openclaw/skills/" flatten bug.
    # `cp -r "path/01-skill" dest/` (no trailing slash) copies the dir as a
    # named subdirectory, producing dest/01-skill/ as intended.
    cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"
    echo "    Updated: $SKILL_NAME"
  done

  # ----------------------------------------------------------
  # v10.15.47: WIRING PHASE — per-skill executed steps (not prose).
  # For every installed skill folder, this phase:
  #   1. Runs the skill's own installer (wire.sh > install.sh > setup-*.sh) if present, idempotent.
  #   2. Idempotently merges CORE_UPDATES.md into workspace AGENTS/TOOLS/MEMORY/SOUL files.
  #   3. Installs OS prereqs (imagemagick/ffmpeg) via brew (Mac) idempotently.
  #   4. Wires skill 36's GHL MCP under nested mcp.servers via `openclaw mcp set`.
  #
  # State guard: each skill writes a sentinel file $SKILLS_DIR/<skill>/.wired-<version>
  # so the loop is safe to re-run — it skips already-wired skills.
  #
  # Scope: additive only. Never edits IDENTITY.md, never rebuilds workforce,
  # never clobbers existing AGENTS.md sections — only appends new ones.
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
    # Sections are delimited by lines matching: ## <TARGET>.md — UPDATE REQUIRED
    # or: ## <TARGET>.md — NO UPDATE NEEDED  (skip those).
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

# Split on section headers like: ## AGENTS.md — UPDATE REQUIRED
# or ## AGENTS.md — NO UPDATE NEEDED
header_re = re.compile(
    r'^##\s+(AGENTS|TOOLS|MEMORY|SOUL)\.md\s*[—–-]+\s*(.*?)$',
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
    [ -z "$BREW_CMD" ] && { echo "    (brew not found — skipping prereqs for $SKILL_FOLDER)"; return 0; }

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
      echo "    (openclaw CLI not found — skipping GHL MCP registration)"
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
        echo "    Installer reported warnings for $SKILL_NAME (see $LOG_FILE) — continuing"
      fi
    fi

    # Step 2: Idempotently merge CORE_UPDATES.md into workspace files
    wire_core_updates "$SKILL_NAME"

    # Step 3: Install OS prereqs (ffmpeg/imagemagick for video skills)
    wire_prereqs "$SKILL_NAME"

    # Step 4: Wire GHL MCP (skill 36 only)
    wire_ghl_mcp "$SKILL_NAME"

    # Mark skill as wired for this version
    touch "$WIRED_SENTINEL" 2>/dev/null || true
    WIRED_COUNT=$((WIRED_COUNT + 1))
  done

  echo "  Wiring complete: $WIRED_COUNT skill(s) wired, $SKIPPED_WIRED_COUNT already wired (idempotent skip)"

  # ----------------------------------------------------------
  # v10.15.42: Run migrate-existing-workforce.sh so copied skills
  # actually install into the client's live department tree.
  # This script is idempotent and additive — it never deletes or
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
    echo "  (migrate-existing-workforce.sh not found or not executable — skipping)"
  fi

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
  # dir — fail loudly instead of reporting false success.
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

  echo ""
  echo "============================================"
  echo "   Skills updated successfully!"
  echo "   Version: $ONBOARDING_VERSION"
  echo "   Location: $SKILLS_DIR"
  echo "   Verified: $VERIFY_SKILL_COUNT skill folders confirmed in active dir"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE — only [$ONLY_SKILLS]"
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
        [ -d "/data/.openclaw" ] && REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main"
        if curl -fsSL --max-time 15 "${REPO_URL}/cron-prompt.txt" -o "$PROMPT_TMP" 2>/dev/null && [ -s "$PROMPT_TMP" ]; then
          PROMPT_CONTENT=$(cat "$PROMPT_TMP")
          if openclaw cron create \
              --name "weekly-onboarding-update" \
              --description "Sunday 2am ET — check for OpenClaw onboarding + command-center updates and ask client permission before applying anything." \
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
            echo "  ⚠ Cron install failed — agent can retry manually"
          fi
          rm -f "$PROMPT_TMP"
        else
          echo "  ⚠ Could not fetch cron-prompt.txt — agent can install cron manually later"
        fi
      else
        echo "  ⚠ No telegram target configured — skipping cron install. Configure Telegram first then re-run."
      fi
    fi
  fi

  # ----------------------------------------------------------
  # Fleet standards: ensure sub-agents fully permitted + Telegram media 50MB
  # (idempotent — applied on every update, no-op if already canonical)
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
  if [ -x "$QC_COMPLETENESS_SCRIPT" ]; then
    echo ""
    echo "  Running qc-completeness.sh against live workforce..."
    QC_OUTPUT="$(bash "$QC_COMPLETENESS_SCRIPT" 2>&1 || true)"
    QC_STATUS_LINE="$(printf '%s\n' "$QC_OUTPUT" | grep -E '^STATUS:' | tail -1)"
    echo "  ${QC_STATUS_LINE:-qc-completeness ran (no STATUS line captured)}"
  fi

  # ----------------------------------------------------------
  # Post-update: write UPDATE PENDING flag + Telegram + backup block
  # ----------------------------------------------------------
  echo ""
  echo "  Writing UPDATE PENDING flag for agent activation..."
  write_update_pending_flag "$ONBOARDING_VERSION" "$NEW_SKILLS_CSV"

  echo "  Sending Telegram notification..."
  send_telegram_progress "✅ OpenClaw skill update ${ONBOARDING_VERSION} complete.

New skills (need activation): ${NEW_SKILLS_CSV:-none — updates only}.

Workforce QC: ${QC_STATUS_LINE:-not run}

Paste this to your agent:

▶ \"I just ran update-skills.sh. There is an UPDATE PENDING flag at the top of my AGENTS.md describing what changed. Please follow the activation steps for any new skills listed. Run QC after each one. Send me a summary when complete.\"

(If you didn't get THIS Telegram note, the same instructions are also printed in your Terminal.)"

  case "$TELEGRAM_LAST_RESULT" in
    sent:*)              echo "  ✓ Telegram sent to ${TELEGRAM_LAST_RESULT#sent:}" ;;
    no-openclaw-cli)     echo "  ⚠ Telegram skipped — openclaw CLI not on PATH" ;;
    no-telegram-target)  echo "  ⚠ Telegram skipped — no telegram.allowFrom configured in openclaw.json" ;;
    failed:*)            echo "  ⚠ Telegram FAILED — see $LOG_FILE (using backup block below)" ;;
  esac

  # Always print the backup block so client is never stranded
  cat <<'BACKUP_BLOCK'

╔════════════════════════════════════════════════════════════════════╗
║   BACKUP — IF YOU DID NOT GET A TELEGRAM NOTE                      ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   Open whatever you use to talk to your OpenClaw agent (Telegram,  ║
║   web UI, terminal chat — whatever you have set up).               ║
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
