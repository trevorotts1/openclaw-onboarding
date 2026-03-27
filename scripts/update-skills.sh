#!/bin/bash
# OpenClaw Onboarding — Update Staging Script
# Version: 4.0 | March 27, 2026
#
# This script STAGES an update. It does NOT apply changes.
# The agent follows UPDATE-PLAYBOOK.md to apply changes intelligently.
#
# After staging, this script generates a client-friendly notification message
# at /tmp/oc-update-notification.md that the agent reads and sends to the client.

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
STAGED_DIR="/tmp/oc-update"
STAGED_ZIP="/tmp/oc-update.zip"
FLAG_FILE="$HOME/.openclaw/skills/.update-pending"
NOTIFICATION_FILE="/tmp/oc-update-notification.md"
LOG_FILE="$HOME/.openclaw/skills/.update-log"

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

# Generate the client-friendly notification message
cat > "$NOTIFICATION_FILE" << NOTEOF
# BlackCEO System Update Available

**Your current version:** $LOCAL_VERSION
**New version available:** $REMOTE_VERSION

An update has been downloaded to your system and is ready to install. This update is NOT affecting your system right now — it is just sitting in a temporary folder waiting for your go-ahead.

## What I Found

I checked your BlackCEO system against the latest version on GitHub. There are updates available that include improvements, bug fixes, and new features.

To see exactly what changed, check the changelog at:
https://github.com/trevorotts1/openclaw-onboarding/blob/main/CHANGELOG.md

## What Happens If You Say Yes

I will:
1. Back up everything important first (your settings, your data, your workflows)
2. Compare what is different between your version and the new version
3. Install only what has changed — nothing else gets touched
4. Check that everything still works after installing

Nothing will break. Nothing will be deleted. Your system keeps running the whole time.

## What I Need From You

Just say **yes** and I will handle everything. Or say **no** and I will not touch anything — the update will just sit there until you are ready.

NOTEOF

echo "Notification message generated at: $NOTIFICATION_FILE"

# Write flag to AGENTS.md so the agent sees it on startup
AGENTS_FILE="$HOME/.openclaw/workspace/AGENTS.md"
if [ -f "$AGENTS_FILE" ]; then
    # Only add if not already there
    if ! grep -q "UPDATE PENDING" "$AGENTS_FILE" 2>/dev/null; then
        cat >> "$AGENTS_FILE" << 'UPDATEFLAG'

## 🔴 UPDATE PENDING — An update has been found and is ready to install. Read /tmp/oc-update-notification.md for the full client summary. Send that message to the client. Then follow /tmp/oc-update/openclaw-onboarding-main/UPDATE-PLAYBOOK.md step by step. Remove this flag when complete.
UPDATEFLAG
    fi
fi

echo ""
echo "============================================"
echo "  NEXT STEPS"
echo "============================================"
echo ""
echo "  Step 1: Restart your gateway by running this command:"
echo ""
echo "    openclaw gateway restart"
echo ""
echo "  Step 2: After it restarts, your AI agent will see the"
echo "          UPDATE PENDING flag in AGENTS.md and will read"
echo "          the client notification from /tmp/oc-update-notification.md"
echo ""
echo "  Step 3: The agent will send you the notification message"
echo "          and ask if you want to install the update."
echo ""
echo "  Step 4: Say 'yes' and the agent will handle everything."
echo ""
echo "  You do NOT need to do anything else. Your agent will"
echo "  take care of the rest."
echo ""
echo "============================================"

# Log the check
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Update check: $LOCAL_VERSION → $REMOTE_VERSION (staged, awaiting approval)" >> "$LOG_FILE"
