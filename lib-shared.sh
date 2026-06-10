#!/usr/bin/env bash
# ============================================================
#  OpenClaw Onboarding — Shared Library Functions (v1.0.1)
#
#  Sourced by install.sh, update-skills.sh, check-updates.sh, and
#  any skill that needs platform detection or master-files lookup.
#
#  All functions here are platform-aware (Mac vs VPS) and use
#  CANONICAL paths and CANONICAL env-var names.
#
#  PRD 2.1 unified — this file is the single shared copy for
#  both mac and vps platforms. Platform overlays live in
#  platform/mac/ and platform/vps/.
# ============================================================

# ----------------------------------------------------------
# Platform detection
# ----------------------------------------------------------
detect_platform() {
  if [ -d "/data/.openclaw" ]; then
    echo "vps"
  else
    echo "mac"
  fi
}

resolve_platform_paths() {
  if [ -d "/data/.openclaw" ]; then
    export OPENCLAW_PLATFORM="vps"
    export OPENCLAW_HOME="/data"
    export SECRETS_ENV="/data/.openclaw/secrets/.env"
    export CONFIG_JSON="/data/.openclaw/openclaw.json"
    export WORKSPACE="/data/.openclaw/workspace"
    export CANONICAL_MASTER="/data/Downloads/openclaw-master-files"
    export SKILLS_DIR_DEFAULT="/data/.openclaw/skills"
    export BACKUP_DIR_DEFAULT="$HOME/openclaw-backups"
  else
    export OPENCLAW_PLATFORM="mac"
    export OPENCLAW_HOME="$HOME"
    export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
    export CONFIG_JSON="$HOME/.openclaw/openclaw.json"
    export WORKSPACE="$HOME/.openclaw/workspace"
    export WORKSPACE_LEGACY="$HOME/clawd"  # dead legacy path — read-only migration only
    export CANONICAL_MASTER="$HOME/Downloads/openclaw-master-files"
    export SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"
    export BACKUP_DIR_DEFAULT="$HOME/Downloads/openclaw-backups"
  fi
}

# ----------------------------------------------------------
# Master-files folder fuzzy locator
#
# Catches all common name variants:
#   openclaw-master-files
#   OpenClaw Master Files (two words, spaces)
#   openclaw_master_files (underscores)
#   open-claw-master-files (hyphen between "open" and "claw")
#   open claw master files (all spaces)
#   OpenClawMasterFiles (camel case)
#   OpenClaw Documents / openclaw files / etc.
#
# Returns: absolute path of detected folder, or empty string.
# ----------------------------------------------------------
find_master_files() {
  local FOUND=""
  local ROOTS=(
    "$HOME/Downloads"
    "/data/Downloads"
    "/root/Downloads"
    "/data"
    "$HOME"
    "$HOME/clawd"
    "/data/.openclaw/workspace"
    "/opt"
    "/srv"
  )

  for r in "${ROOTS[@]}"; do
    [ -d "$r" ] || continue
    # Two-arm pattern: "openclaw" as one token OR "open claw" as two tokens.
    # Case-insensitive. Excludes backup/zip/bak/tmp folders.
    FOUND=$(find "$r" -maxdepth 2 -type d \
      \( \
        -iname "*openclaw*master*file*" -o \
        -iname "*open*claw*master*file*" -o \
        -iname "*openclaw*master*doc*" -o \
        -iname "*open*claw*master*doc*" -o \
        -iname "*openclaw*document*" -o \
        -iname "*open*claw*document*" \
      \) \
      ! -iname "*backup*" \
      ! -iname "*.zip*" \
      ! -iname "*.bak*" \
      ! -iname "*tmp*" \
      2>/dev/null | head -1)
    [ -n "$FOUND" ] && break
  done

  echo "$FOUND"
}

# Get-or-create. Creates at canonical path if not found.
get_or_create_master_files() {
  resolve_platform_paths
  local FOUND
  FOUND=$(find_master_files)
  if [ -n "$FOUND" ]; then
    echo "$FOUND"
    return 0
  fi
  mkdir -p "$CANONICAL_MASTER"
  echo "$CANONICAL_MASTER"
  return 0
}

# ----------------------------------------------------------
# GHL alias awareness
# Returns 0 if the given string refers to GHL/GoHighLevel/etc.
# ----------------------------------------------------------
is_ghl_alias() {
  local s
  s=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]_-')
  case "$s" in
    ghl|gohighlevel|highlevel|convertandflow|leadconnector|leadconnectorhq|cnf)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# ----------------------------------------------------------
# Canonical GHL credential env-var names
#
# NOTE on the env-var name "GOHIGHLEVEL_API_KEY":
#   This is a LEGACY name. Its value is NOT an API key — it is a
#   Private Integration Token (PIT). GoHighLevel stopped issuing
#   API keys ~2 years ago. Every skill that uses this env var
#   treats the value as a PIT. Do not rename this variable —
#   too many skills reference it.
# ----------------------------------------------------------
canonical_ghl_pit_name() {
  echo "GOHIGHLEVEL_API_KEY"
}

canonical_ghl_location_id_name() {
  echo "GOHIGHLEVEL_LOCATION_ID"
}

# Reads GHL PIT from canonical → JSON → deprecated names. Empty if not found.
read_ghl_pit() {
  resolve_platform_paths
  local v=""
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env"; do
    [ -f "$f" ] || continue
    v=$(grep -E "^GOHIGHLEVEL_API_KEY=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [ -n "$v" ] && echo "$v" && return 0
  done
  for j in "$CONFIG_JSON" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -f "$j" ] || continue
    v=$(python3 -c "
import json
try:
  cfg=json.load(open('$j'))
  print(cfg.get('env',{}).get('vars',{}).get('GOHIGHLEVEL_API_KEY',''))
except: pass
" 2>/dev/null)
    [ -n "$v" ] && echo "$v" && return 0
  done
  # Fall to deprecated names (migration path)
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env"; do
    [ -f "$f" ] || continue
    for name in GHL_API_KEY GHL_PRIVATE_TOKEN GHL_PIT; do
      v=$(grep -E "^${name}=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
      [ -n "$v" ] && echo "$v" && return 0
    done
  done
  echo ""
}

read_ghl_location_id() {
  resolve_platform_paths
  local v=""
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env"; do
    [ -f "$f" ] || continue
    v=$(grep -E "^GOHIGHLEVEL_LOCATION_ID=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [ -n "$v" ] && echo "$v" && return 0
  done
  for j in "$CONFIG_JSON" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -f "$j" ] || continue
    v=$(python3 -c "
import json
try:
  cfg=json.load(open('$j'))
  print(cfg.get('env',{}).get('vars',{}).get('GOHIGHLEVEL_LOCATION_ID',''))
except: pass
" 2>/dev/null)
    [ -n "$v" ] && echo "$v" && return 0
  done
  for f in "$SECRETS_ENV" "$HOME/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env"; do
    [ -f "$f" ] || continue
    v=$(grep -E "^GHL_LOCATION_ID=" "$f" 2>/dev/null | head -1 | cut -d'=' -f2-)
    [ -n "$v" ] && echo "$v" && return 0
  done
  echo ""
}
