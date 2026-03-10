#!/usr/bin/env bash
set -euo pipefail

ONBOARDING_VERSION="v2.2.1"

# ============================================================
#  OpenClaw Onboarding Installer
#  Run via: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
# ============================================================

echo ""
echo "============================================"
echo "   OpenClaw Onboarding Installer"
echo "   Version: ${ONBOARDING_VERSION}"
echo "============================================"
echo ""

# ----------------------------------------------------------
# Step 1: Check that OpenClaw CLI is installed
# ----------------------------------------------------------
echo "[1/7] Checking for OpenClaw CLI..."
if ! command -v openclaw &>/dev/null; then
  echo ""
  echo "ERROR: OpenClaw CLI not found in PATH."
  echo ""
  echo "Install OpenClaw first, then re-run this installer:"
  echo "  npm install -g openclaw"
  echo ""
  echo "After installing, run:"
  echo '  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash'
  exit 1
fi
echo "  Found: $(command -v openclaw)"

# ----------------------------------------------------------
# Step 2: Download the onboarding package from GitHub
# ----------------------------------------------------------
echo ""
echo "[2/7] Downloading onboarding package from GitHub..."
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
echo "[3/7] Extracting to ~/.openclaw/onboarding/..."
ONBOARDING_DIR="$HOME/.openclaw/onboarding"
mkdir -p "$ONBOARDING_DIR"

rm -rf "$TEMP_EXTRACT"
unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT"
if [ ! -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
  echo "ERROR: Unexpected archive structure. Expected openclaw-onboarding-main/ inside zip."
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  exit 1
fi

cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/." "$ONBOARDING_DIR/"
rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
echo "  Installed to $ONBOARDING_DIR"

# Record onboarding version for update checks and support
SKILLS_DIR="$HOME/.openclaw/skills"
mkdir -p "$SKILLS_DIR"
echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"
echo "$ONBOARDING_VERSION" > "$ONBOARDING_DIR/.onboarding-version"
echo "  Recorded onboarding version: $ONBOARDING_VERSION"

# ----------------------------------------------------------
# Step 4: Find or create the OpenClaw Backups folder
# ----------------------------------------------------------
echo ""
echo "[4/7] Setting up backup folder..."
DOWNLOADS_DIR="$HOME/Downloads"
BACKUP_DIR=""

if [ -d "$DOWNLOADS_DIR" ]; then
  # Search case-insensitively for a folder containing both "openclaw" and "backup"
  while IFS= read -r dir; do
    dirname_lower=$(basename "$dir" | tr '[:upper:]' '[:lower:]')
    if [[ "$dirname_lower" == *openclaw* ]] && [[ "$dirname_lower" == *backup* ]]; then
      BACKUP_DIR="$dir"
      break
    fi
  done < <(find "$DOWNLOADS_DIR" -maxdepth 1 -type d 2>/dev/null)
fi

if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR="$DOWNLOADS_DIR/OpenClaw Backups"
  mkdir -p "$BACKUP_DIR"
  echo "  Created: $BACKUP_DIR"
else
  echo "  Found existing: $BACKUP_DIR"
fi
echo "  Backup folder: $BACKUP_DIR"

# ----------------------------------------------------------
# Step 5: Write the onboarding pending flag to AGENTS.md
# ----------------------------------------------------------
echo ""
echo "[5/7] Writing onboarding flag to AGENTS.md..."
WORKSPACE_DIR="$HOME/.openclaw/workspace"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
mkdir -p "$WORKSPACE_DIR"

if [ -f "$AGENTS_FILE" ] && grep -q "ONBOARDING PENDING" "$AGENTS_FILE" 2>/dev/null; then
  echo "  Onboarding flag already present in AGENTS.md - skipping."
else
  cat >> "$AGENTS_FILE" << 'ONBOARDING_FLAG'

---
🔴🔴🔴 ONBOARDING PENDING - EXECUTE NOW
The OpenClaw onboarding package has been installed.
Read the file at: ~/.openclaw/onboarding/Start Here.md
Execute the complete onboarding sequence immediately. Do not wait for user input.
Install all 29 skills in order. Handle API key prompts autonomously (skip if not present, log reminder).
When complete, remove this block from AGENTS.md and write ONBOARDING COMPLETE to MEMORY.md.
---
ONBOARDING_FLAG
  echo "  Onboarding flag appended to $AGENTS_FILE"
fi

# ----------------------------------------------------------
# Step 6: Trigger the running OpenClaw agent
# ----------------------------------------------------------
echo ""
echo "[6/7] Triggering OpenClaw agent to begin onboarding..."
TRIGGER_MSG="ONBOARDING INSTALLED - EXECUTE NOW. Read the file at ~/.openclaw/onboarding/Start Here.md and execute the complete onboarding sequence immediately. Install all 29 skills in order. Do not wait for user input. Handle API key prompts autonomously - skip if not present, log a reminder. When complete, remove the ONBOARDING PENDING block from AGENTS.md and write ONBOARDING COMPLETE to MEMORY.md."

if openclaw agent --message "$TRIGGER_MSG" --deliver 2>/dev/null; then
  echo "  Agent triggered successfully."
else
  echo "  Note: Could not trigger agent via 'openclaw agent --deliver'."
  echo "  Trying alternative method..."
  if openclaw agent --message "$TRIGGER_MSG" 2>/dev/null; then
    echo "  Agent turn completed (check your messaging channel for delivery)."
  else
    echo "  Warning: Could not trigger agent automatically."
    echo "  The onboarding flag has been written to AGENTS.md."
    echo "  Your agent will pick it up on its next session start."
    echo "  You can also manually tell your agent: 'Read ~/.openclaw/onboarding/Start Here.md and begin onboarding.'"
  fi
fi

# ----------------------------------------------------------
# Step 7: Done
# ----------------------------------------------------------
echo ""
echo "============================================"
echo "  Onboarding triggered."
echo "  Your OpenClaw agent is now installing"
echo "  29 skills autonomously."
echo "  Installer version: ${ONBOARDING_VERSION}"
echo "  Check your configured messaging channel"
echo "  for progress updates."
echo "============================================"
echo ""
