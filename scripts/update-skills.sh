#!/bin/bash
# OpenClaw Onboarding — Update Staging Script
# Version: 6.1.7 | March 31, 2026
#
# This script STAGES an update. It does NOT apply changes.
# The agent follows UPDATE-PLAYBOOK.md to apply changes intelligently.
#
# After staging, this script:
# 1. Generates a client-friendly notification at /tmp/oc-update-notification.md
# 2. Sends a Telegram message DIRECTLY to the paired user
# 3. If Telegram fails, prints clear fallback instructions in Terminal
# 4. Writes an UPDATE PENDING flag to AGENTS.md so the agent picks it up on restart

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip"
STAGED_DIR="/tmp/oc-update"
STAGED_ZIP="/tmp/oc-update.zip"
FLAG_FILE="$HOME/.openclaw/skills/.update-pending"
NOTIFICATION_FILE="/tmp/oc-update-notification.md"
LOG_FILE="$HOME/.openclaw/skills/.update-log"
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"

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

## 🔴 UPDATE PENDING — IMMEDIATE ACTION REQUIRED. An update for your BlackCEO system has been downloaded and is ready to install. DO THIS RIGHT NOW: 1) Read the file at /tmp/oc-update-notification.md. 2) SEND that message to your client on Telegram IMMEDIATELY. Do not wait for them to message you first. 3) After sending, follow /tmp/oc-update/openclaw-onboarding-main/UPDATE-PLAYBOOK.md step by step. 4) Remove this flag when complete.
UPDATEFLAG
    fi
fi

# ============================================
# SEND TELEGRAM NOTIFICATION DIRECTLY
# ============================================
# Read bot token and first allowFrom chat ID from openclaw.json
# This ensures the user gets notified even if the agent does not pick up the flag

TELEGRAM_SENT=false

if [ -f "$OPENCLAW_CONFIG" ]; then
    # Extract bot token
    BOT_TOKEN=$(python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f:
    d = json.load(f)
tg = d.get('channels', {}).get('telegram', {})
print(tg.get('botToken', ''))
" 2>/dev/null)

    # Extract first allowFrom chat ID (the primary paired user)
    CHAT_ID=$(python3 -c "
import json
with open('$OPENCLAW_CONFIG') as f:
    d = json.load(f)
tg = d.get('channels', {}).get('telegram', {})
af = tg.get('allowFrom', [])
if af:
    print(af[0])
" 2>/dev/null)

    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        # Build the Telegram message
        TG_MESSAGE="🔄 *BlackCEO System Update Available*

Your current version: \`$LOCAL_VERSION\`
New version available: \`$REMOTE_VERSION\`

An update has been downloaded and is ready to install. Nothing has changed yet — it is waiting for your approval.

*STEP 1: Restart your gateway first.*
Run this in Terminal:
\`openclaw gateway restart\`

*STEP 2: After restarting, tell your AI agent this exact message:*
\`Review the update reports and apply approved changes\`

Or just reply *yes* to start the update."

        # Send via Telegram Bot API
        TG_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d chat_id="$CHAT_ID" \
            -d text="$TG_MESSAGE" \
            -d parse_mode="Markdown" 2>&1)

        # Check if send succeeded
        if echo "$TG_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
            TELEGRAM_SENT=true
            echo ""
            echo "[OK] Telegram notification sent to your paired device."
        else
            echo ""
            echo "[WARNING] Could not send Telegram notification."
            echo "          Telegram API response: $TG_RESULT"
        fi
    else
        echo ""
        echo "[WARNING] Could not read Telegram config from openclaw.json."
        echo "          botToken: $([ -n \"$BOT_TOKEN\" ] && echo 'FOUND' || echo 'MISSING')"
        echo "          chatId:  $([ -n \"$CHAT_ID\" ] && echo 'FOUND' || echo 'MISSING')"
    fi
else
    echo ""
    echo "[WARNING] openclaw.json not found. Cannot send Telegram notification."
fi

# ============================================
# TERMINAL OUTPUT — ALWAYS SHOWN
# ============================================
echo ""
echo "============================================"
echo "  UPDATE STAGED SUCCESSFULLY"
echo "============================================"
echo ""

if [ "$TELEGRAM_SENT" = true ]; then
    echo "  A notification was also sent to your Telegram."
    echo ""
fi

echo "  STEP 1: Restart your gateway so your agent"
echo "  can see the update flag:"
echo ""
echo "    openclaw gateway restart"
echo ""
echo "  STEP 2: After restarting, tell your AI agent"
echo "  this exact message:"
echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │                                             │"
echo "  │  Review the update reports and apply        │"
echo "  │  approved changes                           │"
echo "  │                                             │"
echo "  └─────────────────────────────────────────────┘"

echo ""
echo "============================================"

# Log the check
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Update check: $LOCAL_VERSION → $REMOTE_VERSION (staged, awaiting approval) telegram_sent=$TELEGRAM_SENT" >> "$LOG_FILE"
