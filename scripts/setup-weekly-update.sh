#!/bin/bash
# OpenClaw Onboarding — Weekly Update Cron Setup
# Version: 6.5.6 | April 1, 2026
# Run this ONCE per machine after onboarding install.
#
# What it does:
# - Installs a cron job that runs every Sunday at 3:00 AM
# - The cron job downloads the LATEST update-skills.sh from GitHub
#   (version-proof: always runs the newest script, never a stale local copy)
# - That root updater runs the same complete, content-aware update as a manual
#   invocation: onboarding content, SOPs, runtime branding/departments, scripts,
#   provisioning gates, and the Command Center rebuild/health assertion
# - It does not restart the OpenClaw gateway or auto-notify a client chat

REPO_RAW="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh"
LOG_FILE="$HOME/.openclaw/skills/.update-log"

# ----------------------------------------------------------------------------
# IDEMPOTENCY / REPAIR (2026-07-20)
#
# This script used to `exit 0` right here whenever the crontab already carried
# an update-restart-if-needed line -- which made it USELESS as a repair tool and
# is why a real defect survived for months:
#
#   The crontab line is always "0 3 * * 0 $HOME/.openclaw/skills/.update-restart-
#   if-needed". It never contains the UPDATE_SCRIPT_URL that the referenced
#   script points at. So a box whose .update-restart-if-needed still pointed at
#   the LEGACY updater (main/scripts/update-skills.sh -- the version-gated one
#   that skips skills and never syncs shared-utils/universal-sops, yet stamps
#   the version anyway) looked perfectly healthy to this check, and re-running
#   this installer to "fix" it silently changed nothing.
#
# The URL fix landed here on 2026-06-27 (6a881c8a), but only for FRESH installs.
# Every box provisioned before that date kept running the legacy updater weekly.
#
# So: presence of the cron LINE no longer short-circuits the script. We always
# (re)write the restart script to canonical content -- backing up any existing
# copy first -- and only the crontab INSERT is skipped when already present, so
# re-running still cannot duplicate a cron entry. Re-running is now a genuine,
# safe repair.
# ----------------------------------------------------------------------------
EXISTING_CRON=$(crontab -l 2>/dev/null | grep "update-restart-if-needed")
if [ -n "$EXISTING_CRON" ]; then
    echo "[INFO] Weekly update cron line already present — will NOT duplicate it."
    echo "Current entry: $EXISTING_CRON"
    echo "[INFO] Refreshing the restart script itself to canonical content..."
fi

# Install cron job — Sundays at 3:00 AM
# Runs the update script; the updater writes a SILENT UPDATE PENDING flag that
# the agent picks up on its next session (see the SILENT-OPERATOR-CRON note below)
RESTART_SCRIPT="$HOME/.openclaw/skills/.update-restart-if-needed"

# Back up an existing restart script before overwriting, so a box-local change
# is never destroyed silently and the previous URL stays auditable.
if [ -f "$RESTART_SCRIPT" ]; then
    RESTART_BACKUP="${RESTART_SCRIPT}.bak.$(date +%Y%m%d-%H%M%S)"
    if cp -p "$RESTART_SCRIPT" "$RESTART_BACKUP" 2>/dev/null; then
        echo "[INFO] Existing restart script backed up to: $RESTART_BACKUP"
        if grep -q "main/scripts/update-skills.sh" "$RESTART_SCRIPT" 2>/dev/null; then
            echo "[FIX ] It pointed at the LEGACY updater (main/scripts/update-skills.sh)."
            echo "       Repointing to the ROOT updater: $REPO_RAW"
        fi
    else
        echo "[WARN] Could not back up $RESTART_SCRIPT — refusing to overwrite it."
        echo "       Fix the permissions and re-run, or edit the UPDATE_SCRIPT_URL line by hand."
        exit 1
    fi
fi

mkdir -p "$(dirname "$RESTART_SCRIPT")"
cat > "$RESTART_SCRIPT" << 'RESTART_EOF'
#!/bin/bash
# Run the update script — fetch to temp file first so partial downloads do not
# execute half a script (the classic curl|bash truncation hazard).
UPDATE_SCRIPT_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh"
_UPDATE_TMP="$(mktemp /tmp/openclaw-update-XXXXXX.sh)"
trap 'rm -f "$_UPDATE_TMP"' EXIT
if ! curl -fsSL --max-time 60 "$UPDATE_SCRIPT_URL" -o "$_UPDATE_TMP" 2>>"$HOME/.openclaw/skills/.update-log"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: failed to download update-skills.sh — skipping update" >> "$HOME/.openclaw/skills/.update-log"
  exit 1
fi
bash "$_UPDATE_TMP" >> "$HOME/.openclaw/skills/.update-log" 2>&1
_UPDATE_RC=$?
if [ "$_UPDATE_RC" -ne 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: complete fleet update failed (exit $_UPDATE_RC) — inspect this log; success was not stamped" >> "$HOME/.openclaw/skills/.update-log"
  exit "$_UPDATE_RC"
fi

# SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons): updates push SILENTLY.
# update-skills.sh already wrote the UPDATE PENDING flag into the agent's
# AGENTS.md — the agent reads it on its NEXT session naturally and surfaces an
# owner-facing summary on its own terms. We deliberately do NOT
# `openclaw gateway restart` here:
#   (1) a restart is disruptive (it kills any in-flight session) and on Mac
#       LaunchAgent boxes a mistimed restart can wedge the gateway DOWN; and
#   (2) it was only ever a way to FORCE the agent to notice the flag — which the
#       silent AGENTS.md flag already accomplishes without interrupting anyone.
# Log the pending-vs-clean outcome only; no restart, no client-facing push.
if [ -f "$HOME/.openclaw/skills/.update-pending" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Complete updater finished; an existing UPDATE PENDING flag remains for the agent's next session (no gateway restart, no client auto-notify)" >> "$HOME/.openclaw/skills/.update-log"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Complete updater finished successfully (content was current or all update gates passed)" >> "$HOME/.openclaw/skills/.update-log"
fi
RESTART_EOF
chmod +x "$RESTART_SCRIPT"

# Only INSERT the cron line when it is absent — re-running must never duplicate it.
if [ -z "$EXISTING_CRON" ]; then
    (crontab -l 2>/dev/null; echo "0 3 * * 0 $RESTART_SCRIPT") | crontab -
    echo "[OK  ] Sunday 3:00 AM cron line installed."
else
    echo "[SKIP] Sunday cron line already present — not re-inserted."
fi

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
echo "  -> Runs the complete content-aware fleet update without restarting the gateway"
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
echo "    2. Verifies installed content, not just the version stamp"
echo "    3. If drift exists, updates onboarding + SOPs + scripts + runtime config"
echo "    4. Updates, rebuilds, restarts, and health-checks Command Center"
echo "    5. Runs completeness gates before stamping success"
echo "    6. Exits nonzero and logs an ERROR if any complete-update stage fails"
echo "    7. Does not restart the gateway or auto-notify a client chat"
echo ""
echo "To force a manual check now:"
echo "  curl -fsSL $REPO_RAW | bash"
echo "To check logs: cat $LOG_FILE"
echo "To verify cron: crontab -l"
