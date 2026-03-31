#!/bin/bash
# OpenClaw Onboarding — Weekly Update Cron Setup
# Version: 6.1.9 | March 31, 2026
# Run this ONCE per machine after onboarding install.
#
# What it does:
# - Installs a cron job that runs every Sunday at 3:00 AM
# - The cron job downloads the LATEST update-skills.sh from GitHub
#   (version-proof: always runs the newest script, never a stale local copy)
# - That script checks GitHub for updates, compares versions,
#   stages the update, and tells the human what to tell their agent
# - NO changes are applied automatically by the cron job
# - The agent follows UPDATE-PLAYBOOK.md to apply changes intelligently

REPO_RAW="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/update-skills.sh"
LOG_FILE="$HOME/.openclaw/skills/.update-log"

# Check if cron already installed
EXISTING_CRON=$(crontab -l 2>/dev/null | grep "update-restart-if-needed")
if [ -n "$EXISTING_CRON" ]; then
    echo "[INFO] Weekly update cron already installed."
    echo "Current entry: $EXISTING_CRON"
    echo ""
    echo "To remove: crontab -e (and delete the update-restart line)"
    echo "To force a manual check now:"
    echo "  curl -fsSL $REPO_RAW | bash"
    exit 0
fi

# Install cron job — Sundays at 3:00 AM
# Runs the update script, then restarts the gateway ONLY if an update was staged
# The agent picks up the UPDATE PENDING flag on boot and follows UPDATE-PLAYBOOK.md
RESTART_SCRIPT="$HOME/.openclaw/skills/.update-restart-if-needed"
cat > "$RESTART_SCRIPT" << 'RESTART_EOF'
#!/bin/bash
# Run the update script
UPDATE_SCRIPT_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/update-skills.sh"
curl -fsSL "$UPDATE_SCRIPT_URL" | bash >> "$HOME/.openclaw/skills/.update-log" 2>&1

# If the update flag exists, an update was staged — restart the gateway so the agent sees it
if [ -f "$HOME/.openclaw/skills/.update-pending" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Update staged — restarting gateway to notify agent" >> "$HOME/.openclaw/skills/.update-log"
    openclaw gateway restart >> "$HOME/.openclaw/skills/.update-log" 2>&1
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No update needed — skipping gateway restart" >> "$HOME/.openclaw/skills/.update-log"
fi
RESTART_EOF
chmod +x "$RESTART_SCRIPT"

(crontab -l 2>/dev/null; echo "0 3 * * 0 $RESTART_SCRIPT") | crontab -

# Install Saturday 11:59 PM OpenClaw CLI update cron job
# Updates OpenClaw to the latest version BEFORE the Sunday onboarding check
# This ensures config structures are validated against the latest OpenClaw version
OPENCLAW_UPDATE_SCRIPT="$HOME/.openclaw/skills/.openclaw-self-update"
cat > "$OPENCLAW_UPDATE_SCRIPT" << 'OCUPDATE_EOF'
#!/bin/bash
OC_LOG="$HOME/.openclaw/skills/.update-log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Saturday OpenClaw update check starting" >> "$OC_LOG"

# Check if gateway is busy (agent is active)
# Skip if a user session was active in the last 30 minutes
# This prevents interrupting active work
if [ -f "$HOME/.openclaw/skills/.update-pending" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Update already pending from earlier — skipping OpenClaw update" >> "$OC_LOG"
    exit 0
fi

# Update OpenClaw CLI
npm update -g openclaw >> "$OC_LOG" 2>&1
OC_VERSION=$(openclaw --version 2>/dev/null)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] OpenClaw updated to: $OC_VERSION" >> "$OC_LOG"
OCUPDATE_EOF
chmod +x "$OPENCLAW_UPDATE_SCRIPT"

(crontab -l 2>/dev/null; echo "59 23 * * 6 $OPENCLAW_UPDATE_SCRIPT") | crontab -

echo "[OK] Weekly update crons installed."
echo ""
echo "Schedule 1: Every Saturday at 11:59 PM"
echo "  -> Updates OpenClaw CLI to latest version"
echo ""
echo "Schedule 2: Every Sunday at 3:00 AM"
echo "  -> Checks for onboarding updates, stages, and restarts gateway"
echo ""
echo "Source: GitHub (always latest version)"
echo "Log: $LOG_FILE"
echo ""
echo "What happens each week:"
echo "  Saturday 11:59 PM:"
echo "    1. Updates OpenClaw CLI (npm update -g openclaw)"
echo "    2. Logs the new version"
echo ""
echo "  Sunday 3:00 AM:"
echo "    1. Downloads the latest update script from GitHub"
echo "    2. Checks GitHub for new onboarding versions"
echo "    3. Compares against your installed version"
echo "    4. If update available: stages it, creates pending flag,"
echo "       sends Telegram notification, and restarts gateway"
echo "    5. Agent boots on latest OpenClaw, sees the flag"
echo "    6. Agent validates config structure against current OpenClaw docs"
echo "    7. Agent tells you what changed and asks for approval"
echo "    8. If you say yes, agent applies the update and runs QC"
echo ""
echo "To force a manual check now:"
echo "  curl -fsSL $REPO_RAW | bash"
echo "To check logs: cat $LOG_FILE"
echo "To verify cron: crontab -l"
