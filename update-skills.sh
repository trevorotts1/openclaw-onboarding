#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  OpenClaw Skills Updater — Mac Version
#  Updates skills from GitHub to ~/Downloads/openclaw-master-files/
# ============================================================

ONBOARDING_VERSION="v8.3.0"

# ----------------------------------------------------------
# SKILLS DIRECTORY SECTION — How to find skills on Mac
# ----------------------------------------------------------
# Primary Mac location:   ~/Downloads/openclaw-master-files/
# Secondary location:     ~/.openclaw/skills/
# Fallback search:        Any folder matching *openclaw* + *master*
#
# The updater will:
# 1. Check if skills exist at known locations
# 2. Search for skills using fuzzy matching if not found
# 3. Default to ~/Downloads/openclaw-master-files/ for new installs
# ----------------------------------------------------------

# ----------------------------------------------------------
# Discover skills directory — smarter search for Mac
# ----------------------------------------------------------
discover_skills_dir() {
  # Primary Mac location first
  local CANDIDATES=(
    "$HOME/Downloads/openclaw-master-files"
    "$HOME/.openclaw/skills"
    "$HOME/.openclaw/onboarding"
    "$HOME/openclaw-onboarding"
  )

  # Check exact known paths first
  for DIR in "${CANDIDATES[@]}"; do
    if [ -d "$DIR" ]; then
      local SKILL_COUNT=$(ls -d "$DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
      if [ "$SKILL_COUNT" -gt "0" ]; then
        echo "$DIR"
        return
      fi
    fi
  done

  # Fuzzy search for folders with "openclaw" and "master" in name (case-insensitive)
  local FUZZY_DIR=$(find "$HOME" -maxdepth 2 -type d -iname "*openclaw*" 2>/dev/null | grep -i "master" | head -1)
  if [ -n "$FUZZY_DIR" ] && [ -d "$FUZZY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$FUZZY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$FUZZY_DIR"
      return
    fi
  fi

  # Default to Mac canonical location
  echo "$HOME/Downloads/openclaw-master-files"
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
# ----------------------------------------------------------
get_current_version() {
  local VERSION_PATHS=(
    "$HOME/Downloads/openclaw-master-files/.onboarding-version"
    "$HOME/.openclaw/skills/.onboarding-version"
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
  echo "============================================"
  echo "   OpenClaw Skills Updater (Mac)"
  echo "   Version: ${ONBOARDING_VERSION}"
  echo "============================================"
  echo ""

  # Discover skills directory
  SKILLS_DIR=$(discover_skills_dir)
  export SKILLS_DIR
  echo "  📂 Skills directory: $SKILLS_DIR"

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

  # Download and extract
  TEMP_ZIP="/tmp/openclaw-onboarding-update.zip"
  TEMP_EXTRACT="/tmp/openclaw-onboarding-update"

  curl -fSL --progress-bar "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"

  rm -rf "$TEMP_EXTRACT"
  unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT"

  # Find extracted folder
  EXTRACTED_DIR=""
  if [ -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
    EXTRACTED_DIR="$TEMP_EXTRACT/openclaw-onboarding-main"
  else
    EXTRACTED_DIR=$(find "$TEMP_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1)
  fi

  if [ -z "$EXTRACTED_DIR" ] || [ ! -d "$EXTRACTED_DIR" ]; then
    echo "ERROR: Could not find extracted folder"
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
  for SKILL_DIR in "$EXTRACTED_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")

    # Skip archived skills
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # Remove old version if exists
    rm -rf "$SKILLS_DIR/$SKILL_NAME"

    # Copy new version
    cp -r "$SKILL_DIR" "$SKILLS_DIR/"
    echo "    Updated: $SKILL_NAME"
  done

  # Write version file
  echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"

  # Cleanup
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"

  echo ""
  echo "============================================"
  echo "   Skills updated successfully!"
  echo "   Version: $ONBOARDING_VERSION"
  echo "   Location: $SKILLS_DIR"
  echo "============================================"
}

main "$@"
