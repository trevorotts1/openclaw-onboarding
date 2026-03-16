#!/bin/bash
# OpenClaw Onboarding — Weekly Update Cron Setup
# Version: 2.0 | March 16, 2026
# Run this ONCE per machine after onboarding install.
#
# What it does:
# - Installs a cron job that runs every Sunday at 2:00 AM
# - The cron job runs the surgical update-skills.sh script
# - That script checks GitHub for updates, compares versions,
#   generates impact reports, and surfaces recommendations
# - NO changes are made without user approval
# - The agent NEVER triggers a gateway restart

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UPDATE_SCRIPT="$SCRIPT_DIR/update-skills.sh"
LOG_FILE="$HOME/.openclaw/skills/.update-log"

# Ensure update script exists and is executable
if [ ! -f "$UPDATE_SCRIPT" ]; then
    echo "[ERROR] update-skills.sh not found at $UPDATE_SCRIPT"
    exit 1
fi

chmod +x "$UPDATE_SCRIPT"

# Check if cron already installed
EXISTING_CRON=$(crontab -l 2>/dev/null | grep "update-skills.sh")
if [ -n "$EXISTING_CRON" ]; then
    echo "[INFO] Weekly update cron already installed."
    echo "Current entry: $EXISTING_CRON"
    echo ""
    echo "To remove: crontab -e (and delete the update-skills line)"
    echo "To force a manual check now: bash $UPDATE_SCRIPT"
    exit 0
fi

# Install cron job — Sundays at 2:00 AM
(crontab -l 2>/dev/null; echo "0 2 * * 0 bash $UPDATE_SCRIPT >> $LOG_FILE 2>&1") | crontab -

echo "[OK] Weekly update cron installed."
echo ""
echo "Schedule: Every Sunday at 2:00 AM"
echo "Script: $UPDATE_SCRIPT"
echo "Log: $LOG_FILE"
echo ""
echo "What happens each Sunday:"
echo "  1. Checks GitHub for new versions"
echo "  2. Compares against your installed skills"
echo "  3. Generates gap and impact reports"
echo "  4. Surfaces recommendations — does NOT auto-apply"
echo "  5. You review and approve before any changes are made"
echo ""
echo "To force a manual check now: bash $UPDATE_SCRIPT"
echo "To check logs: cat $LOG_FILE"
echo "To verify cron: crontab -l | grep update-skills"
