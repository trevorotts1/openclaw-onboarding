#!/usr/bin/env bash
set -euo pipefail

ONBOARDING_VERSION="v5.0.0"

# ============================================================
#  OpenClaw Onboarding Installer
#  Run via: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
# ============================================================

# ----------------------------------------------------------
# Check if onboarding already in progress
# ----------------------------------------------------------
ONBOARDING_DIR="$HOME/.openclaw/onboarding"
mkdir -p "$ONBOARDING_DIR"
INSTALL_FLAG="$ONBOARDING_DIR/.install-in-progress"

if [ -f "$INSTALL_FLAG" ]; then
  echo ""
  echo "============================================"
  echo "   Onboarding already in progress"
  echo "============================================"
  echo ""
  echo "Another installation process is already running."
  echo "If this is incorrect, you can manually remove the flag:"
  echo "  rm $INSTALL_FLAG"
  echo ""
  exit 0
fi

# Create flag file
touch "$INSTALL_FLAG"
trap 'rm -f "$INSTALL_FLAG"' EXIT

echo ""
echo "============================================"
echo "   OpenClaw Onboarding Installer"
echo "   Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""

# ----------------------------------------------------------
# Step 1: Check that OpenClaw CLI is installed
# ----------------------------------------------------------
echo "[1/5] Checking for OpenClaw CLI..."
if ! command -v openclaw &>/dev/null; then
  echo ""
  echo "ERROR: OpenClaw CLI not found in PATH."
  echo ""
  echo "Install OpenClaw first:"
  echo "  npm install -g openclaw"
  echo ""
  exit 1
fi
echo "  Found: $(command -v openclaw)"

# ----------------------------------------------------------
# Step 2: Download the onboarding package
# ----------------------------------------------------------
echo ""
echo "[2/5] Downloading 31 skills from GitHub..."
TEMP_ZIP="/tmp/openclaw-onboarding-pkg.zip"
TEMP_EXTRACT="/tmp/openclaw-onboarding-extract"

curl -fsSL "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
if [ ! -f "$TEMP_ZIP" ]; then
  echo "ERROR: Failed to download onboarding package."
  exit 1
fi
echo "  Downloaded to $TEMP_ZIP"

# ----------------------------------------------------------
# Step 3: Extract to ~/.openclaw/onboarding/
# ----------------------------------------------------------
echo ""
echo "[3/5] Extracting to ~/.openclaw/onboarding/..."
rm -rf "$TEMP_EXTRACT"
unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT"
if [ ! -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
  echo "ERROR: Unexpected archive structure."
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  exit 1
fi

# Clear existing onboarding folder and copy fresh
cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/"* "$ONBOARDING_DIR/"
rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
echo "  Installed to $ONBOARDING_DIR"

# Count skills
SKILL_COUNT=$(ls -1 "$ONBOARDING_DIR" | grep -E "^[0-9]+-" | wc -l)
echo "  Skills found: $SKILL_COUNT"

# Record version
SKILLS_DIR="$HOME/.openclaw/skills"
mkdir -p "$SKILLS_DIR"
echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"
echo "$ONBOARDING_VERSION" > "$ONBOARDING_DIR/.onboarding-version"
echo "  Version: $ONBOARDING_VERSION"

# ----------------------------------------------------------
# Step 4: Set up backup folder
# ----------------------------------------------------------
echo ""
echo "[4/5] Setting up backup folder..."
DOWNLOADS_DIR="$HOME/Downloads"
BACKUP_DIR=""

# Look for existing backup folder
if [ -d "$DOWNLOADS_DIR" ]; then
  while IFS= read -r dir; do
    dirname_lower=$(basename "$dir" | tr '[:upper:]' '[:lower:]')
    if [[ "$dirname_lower" == *openclaw* ]] && [[ "$dirname_lower" == *backup* ]]; then
      BACKUP_DIR="$dir"
      break
    fi
  done < <(find "$DOWNLOADS_DIR" -maxdepth 1 -type d 2>/dev/null)
fi

# Create if not found
if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR="$DOWNLOADS_DIR/OpenClaw Backups"
  mkdir -p "$BACKUP_DIR"
  echo "  Created: $BACKUP_DIR"
else
  echo "  Found: $BACKUP_DIR"
fi

# ----------------------------------------------------------
# Step 5: Write onboarding flag to AGENTS.md
# ----------------------------------------------------------
echo ""
echo "[5/5] Writing onboarding flag..."
WORKSPACE_DIR="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
mkdir -p "$WORKSPACE_DIR"

# Remove any existing ONBOARDING PENDING flag to avoid duplicates
if [ -f "$AGENTS_FILE" ]; then
  grep -v "ONBOARDING PENDING\|ONBOARDING COMPLETE" "$AGENTS_FILE" > "$AGENTS_FILE.tmp" 2>/dev/null || true
  mv "$AGENTS_FILE.tmp" "$AGENTS_FILE" 2>/dev/null || true
fi

cat >> "$AGENTS_FILE" << 'ONBOARDING_FLAG'

---
🔴🔴🔴 ONBOARDING PENDING - EXECUTE IMMEDIATELY

The OpenClaw onboarding package (31 skills) has been installed to:
  ~/.openclaw/onboarding/

READ THIS FILE FIRST: ~/.openclaw/onboarding/Start Here.md

It contains the complete execution checklist, wave instructions, and failure handling.

SUMMARY:
- Install 31 skills using 5-Wave Parallel Orchestration
- Use parallel sub-agents for Waves 2 and 4 (if sessions_spawn works)
- Use sequential mode for Waves 1, 3, 5
- Skip skill 13 (archived)
- Skills 22-23: Main orchestrator ONLY (no sub-agents)
- Track progress in ~/.openclaw/onboarding/.onboarding-status
- Remove this flag and write ONBOARDING COMPLETE to MEMORY.md when done

DO NOT:
- Skip reading Start Here.md
- Skip skills or say "done" until all 31 complete
- Delegate skills 22-23 to sub-agents
- Trigger gateway restarts without asking

ZERO TOLERANCE SHORTCUTS:
- "I'll read that later" = WRONG. Read it NOW.
- "This looks similar to..." = WRONG. Read every file completely.
- "I can skip this step" = WRONG. Follow every step exactly.
---
ONBOARDING_FLAG

echo "  Onboarding flag written to: $AGENTS_FILE"

# ----------------------------------------------------------
# Done
# ----------------------------------------------------------
echo ""
echo "============================================"
echo "  OpenClaw Onboarding Package Ready"
echo "  Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""
echo "  📦 31 skills downloaded to:"
echo "     ~/.openclaw/onboarding/"
echo ""
echo "  📋 ONBOARDING FLAG LOCATION:"
echo "     $AGENTS_FILE"
echo ""
echo "  📋 Next step: Tell your AI agent to begin."
echo ""
echo "     Send this EXACT message to your OpenClaw agent:"
echo ""
echo "       'Read $AGENTS_FILE and begin onboarding installation'"
echo ""
echo "  The agent will read AGENTS.md, find the"
echo "  ONBOARDING PENDING flag, and install all"
echo "  31 skills automatically."
echo ""
echo "  ⚠️  If the agent says it cannot find the flag,"
echo "     tell it to run:"
echo "     grep -r 'ONBOARDING PENDING' $AGENTS_FILE"
echo ""
echo "============================================"
echo ""
