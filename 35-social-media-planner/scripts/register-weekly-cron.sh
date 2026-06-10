#!/usr/bin/env bash
# ============================================================
#  register-weekly-cron.sh
#  Skill 35 — Social Media Planner / Content Publishing Engine
#
#  Registers the weekly content-theme cron via the OpenClaw
#  gateway cron store (NOT .cron.jobs — that block does not
#  validate on 2026.5.27+).
#
#  Idempotent: checks `openclaw cron list` before registering.
#
#  VPS context: runs inside the Hostinger Docker container
#  where `openclaw` CLI is on PATH. Same pattern as Skill 38's
#  04-register-crons.sh.
#
#  Cron: Saturday 8:00 AM (0 8 * * 6) — weekly theme + plan.
# ============================================================
set -euo pipefail

CRON_NAME="skill35-weekly-theme"
CRON_EXPR="0 8 * * 6"
AGENT_ID="${ROUTING_AGENT_ID:-main}"

command -v openclaw >/dev/null 2>&1 || {
  echo "ERROR: openclaw CLI not on PATH — cannot register cron via the gateway cron store." >&2
  echo "Expose the openclaw CLI and re-run. Do NOT write to .cron.jobs — it does not validate on 2026.5.27+." >&2
  exit 2
}

# Idempotency guard
if openclaw cron list 2>/dev/null | grep -q "$CRON_NAME"; then
  echo "cron '$CRON_NAME' already registered — nothing to do." >&2
  exit 0
fi

CRON_MESSAGE="Skill 35 weekly trigger: Ask the owner what content theme they want for the coming week. After they reply (or after 1 hour with no reply, use 'evergreen'), run the weekly social media planning cycle: read \$HOME/.openclaw/config/content-calendar.json, fire \$HOME/.openclaw/skills/35-social-media-planner/scripts/run-publishing-cycle.sh for all topics due this week. Check state marker /tmp/skill35-weekly-theme-\$(date +%Y%U).done before acting — if it exists, the week's theme request already fired this week; skip gracefully. After completing, write that marker file so re-fires are idempotent."

if openclaw cron add \
     --name "$CRON_NAME" \
     --cron "$CRON_EXPR" \
     --agent "$AGENT_ID" \
     --message "$CRON_MESSAGE" \
     --light-context \
     --announce \
     --channel last \
     --best-effort-deliver; then
  echo "OK: cron '$CRON_NAME' registered ($CRON_EXPR — Saturday 8:00 AM weekly)." >&2
else
  echo "ERROR: failed to register cron '$CRON_NAME' via 'openclaw cron add'" >&2
  exit 1
fi

# Validate config is still clean after registering
if command -v openclaw >/dev/null 2>&1; then
  openclaw config validate || {
    echo "ERROR: openclaw config validate FAILED after cron registration" >&2
    exit 5
  }
fi

echo "OK: Skill 35 weekly-theme cron registered and config validated." >&2
