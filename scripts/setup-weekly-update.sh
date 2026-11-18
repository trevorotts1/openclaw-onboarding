#!/bin/bash
# OpenClaw Onboarding -- automatic update schedule setup (Tuesday / Friday / Sunday).
# Run this ONCE per machine after onboarding install; update-skills.sh runs it again on every update, and
# re-running it changes nothing when the box is already set up.
#
# What the box does after this (all of it deterministic script work, no model decides timing or rollback):
#   - ONE crontab line, every 5 minutes, runs scripts/auto-update-tick.sh. The tick keeps its own
#     America/New_York clock (daylight saving handled inside the script, independent of the box time zone).
#   - Tuesday, Friday and Sunday at 2:15 AM Eastern: ONE notice in the owner's main chat:
#       "Heads up: I'll start updating your system in 15 minutes (2:30 AM). Type cancel if you want to skip this update."
#   - 2:30 AM Eastern plus a random 0-15 minute offset per box: the update run, unless the owner typed the
#     word cancel after the notice (that skips this run only and gets one short reply).
#   - A run takes the shared box update lock, checks onboarding, Command Center and (macOS only) 999-setup against
#     GitHub, updates ONLY what is behind, snapshots first, applies, health-gates, repairs, and rolls back if it
#     cannot repair, then writes a one-line status beacon (~/.openclaw/skills/.auto-update-status.json).
#   - The OpenClaw CLI update runs inside that same run, before the health gate.
#
# What this script retires (so nothing collides): the old Sunday 3:00 AM crontab line
# (.update-restart-if-needed), the old Saturday 11:59 PM OpenClaw self-update crontab line
# (.openclaw-self-update), and every openclaw cron job named weekly-onboarding-update (the old agent
# "ask first" job and the 2:00 AM command job).
#
# Usage:  bash scripts/setup-weekly-update.sh [--dry-run]
# Never restarts the gateway, never messages a client, never touches credentials, models or departments.

set -u
SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
DRY=""
case "${1:-}" in
  --dry-run) DRY="--dry-run" ;;
  "") ;;
  *) echo "Usage: setup-weekly-update.sh [--dry-run]" >&2; exit 2 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "[FAIL] python3 is required to install the update schedule" >&2
  exit 1
fi
if [ ! -f "$SELF_DIR/auto_update.py" ]; then
  echo "[FAIL] $SELF_DIR/auto_update.py is missing: run this from a current onboarding copy" >&2
  exit 1
fi

python3 "$SELF_DIR/auto_update.py" install $DRY || exit $?

echo ""
echo "[OK] Automatic update schedule is in place."
echo ""
echo "Schedule (America/New_York, daylight saving handled): Tuesday, Friday and Sunday"
echo "  2:15 AM  one notice in your main chat: the update starts in 15 minutes, type cancel to skip it"
echo "  2:30 AM  the update starts (plus a random 0-15 minutes), only if something is behind"
echo ""
echo "Each run: lock the box, check versions, snapshot, update, health check, repair, roll back if needed."
echo "Status of the last run: cat ~/.openclaw/skills/.auto-update-status.json"
echo "Log:                    ~/.openclaw/skills/.update-log"
echo "Verify the schedule:    crontab -l | grep openclaw-auto-update"
echo "Next runs:              python3 $SELF_DIR/auto_update.py next"
