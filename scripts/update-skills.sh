#!/bin/bash
# OpenClaw Onboarding — Update Staging Script
# Version: 3.0 | March 25, 2026
#
# This script STAGES an update. It does NOT apply changes.
# The agent follows UPDATE-PLAYBOOK.md to apply changes intelligently.

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
STAGED_DIR="/tmp/oc-update"
STAGED_ZIP="/tmp/oc-update.zip"
FLAG_FILE="$HOME/.openclaw/skills/.update-pending"

echo ""
echo "============================================"
echo "   BlackCEO System — Update Check"
echo "============================================"
echo ""

# Check current version
LOCAL_VERSION="unknown"
if [ -f "$HOME/.openclaw/skills/.onboarding-version" ]; then
    LOCAL_VERSION=$(cat "$HOME/.openclaw/skills/.onboarding-version")
fi
echo "Current version: $LOCAL_VERSION"

# Download latest
echo ""
echo "Downloading latest version from GitHub..."
rm -rf "$STAGED_DIR" "$STAGED_ZIP"
curl -fsSL "$REPO_URL" -o "$STAGED_ZIP" 2>/dev/null

if [ ! -f "$STAGED_ZIP" ]; then
    echo "[ERROR] Could not download update. Check your internet connection."
    exit 1
fi

# Extract
unzip -qo "$STAGED_ZIP" -d "$STAGED_DIR"
if [ ! -d "$STAGED_DIR/openclaw-onboarding-main" ]; then
    echo "[ERROR] Unexpected archive structure."
    rm -rf "$STAGED_DIR" "$STAGED_ZIP"
    exit 1
fi

# Check remote version
REMOTE_VERSION="unknown"
if [ -f "$STAGED_DIR/openclaw-onboarding-main/version" ]; then
    REMOTE_VERSION=$(cat "$STAGED_DIR/openclaw-onboarding-main/version")
fi
echo "Latest version:  $REMOTE_VERSION"

# Compare
if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ]; then
    echo ""
    echo "You are already on the latest version ($LOCAL_VERSION)."
    echo "No update needed."
    rm -rf "$STAGED_DIR" "$STAGED_ZIP"
    exit 0
fi

# Stage the update
echo ""
echo "Update available: $LOCAL_VERSION → $REMOTE_VERSION"
echo ""

# Create flag file
touch "$FLAG_FILE"

echo "Update staged successfully."
echo ""
echo "============================================"
echo "  NEXT STEPS"
echo "============================================"
echo ""
echo "  Step 1: Restart your gateway by running this command:"
echo ""
echo "    openclaw gateway restart"
echo ""
echo "  Step 2: After it restarts, go to your AI agent in Telegram"
echo "          and send it this exact message:"
echo ""
echo '    "There is an update staged in /tmp/oc-update. Read /tmp/oc-update/openclaw-onboarding-main/UPDATE-PLAYBOOK.md and follow it step by step. Report back when done."'
echo ""
echo "  That's it. Your AI will handle the rest."
echo "  It will only update what has changed — nothing else."
echo ""
echo "============================================"
