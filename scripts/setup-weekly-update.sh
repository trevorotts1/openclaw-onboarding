#!/bin/bash
# OpenClaw Onboarding — Weekly Update Cron Setup
# Version: 6.1.7 | March 31, 2026
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
EXISTING_CRON=$(crontab -l 2>/dev/null | grep "update-skills.sh")
if [ -n "$EXISTING_CRON" ]; then
    echo "[INFO] Weekly update cron already installed."
    echo "Current entry: $EXISTING_CRON"
    echo ""
    echo "To remove: crontab -e (and delete the update-skills line)"
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

echo "[OK] Weekly update cron installed."
echo ""
echo "Schedule: Every Sunday at 3:00 AM"
echo "Source: GitHub (always latest version)"
echo "Log: $LOG_FILE"
echo ""
echo "What happens each Sunday:"
echo "  1. Downloads the latest update script from GitHub"
echo "  2. Checks GitHub for new onboarding versions"
echo "  3. Compares against your installed version"
echo "  4. If update available: stages it, creates pending flag,"
echo "     sends Telegram notification, and restarts gateway"
echo "  5. Agent boots, sees the flag, reviews changelog"
echo "  6. Agent tells you what changed and asks for approval"
echo "  7. If you say yes, agent applies the update and runs QC"
echo ""
echo "To force a manual check now:"
echo "  curl -fsSL $REPO_RAW | bash"
echo "To check logs: cat $LOG_FILE"
echo "To verify cron: crontab -l | grep update-skills"
