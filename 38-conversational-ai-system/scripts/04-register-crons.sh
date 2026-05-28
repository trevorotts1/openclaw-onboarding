#!/usr/bin/env bash
# 04-register-crons.sh — Skill 38 cron registrations (v5.14)
# Sunday 2am weekly-tune-up · Saturday 11pm proactive-suggestions-scan + model-version-freshness · 1st-of-month system-health-heartbeat
# Idempotent (skips if entry already exists). Uses openclaw cron when available; falls back to crontab.

set -euo pipefail

register() {
  local name="$1" schedule="$2" prompt_or_cmd="$3"
  if command -v openclaw >/dev/null 2>&1; then
    if openclaw cron list 2>/dev/null | grep -q " $name "; then
      echo "[skill 38] cron '$name' already exists"
      return 0
    fi
    openclaw cron create --schedule "$schedule" --name "$name" --prompt "$prompt_or_cmd" >/dev/null 2>&1 || \
      openclaw cron add --schedule "$schedule" --name "$name" --prompt "$prompt_or_cmd" >/dev/null 2>&1 || true
    echo "[skill 38] registered openclaw cron '$name' ($schedule)"
  else
    # Fallback: system crontab. Idempotent via marker.
    local marker="# [skill38:$name]"
    if crontab -l 2>/dev/null | grep -q "$marker"; then
      echo "[skill 38] crontab '$name' already present"
      return 0
    fi
    ( crontab -l 2>/dev/null; echo "$schedule $prompt_or_cmd $marker" ) | crontab -
    echo "[skill 38] added crontab entry '$name' ($schedule)"
  fi
}

# Sunday 2am — weekly conversation AI tune-up (Step 9.32)
register "weekly-tune-up" "0 2 * * 0" "Run the weekly conversation AI tune-up per protocols/weekly-tune-up-protocol.md"
# Saturday 11pm — proactive suggestions scan + model version freshness (Steps 9.34, 9.36)
register "proactive-suggestions-scan" "0 23 * * 6" "Run proactive suggestions scan per protocols/proactive-suggestions-protocol.md"
register "model-version-freshness"    "30 23 * * 6" "Check model version freshness per protocols/model-version-freshness-protocol.md"
# 1st of month — monthly comprehensive playbook review (Step 9.35)
register "monthly-comprehensive-review" "0 3 1 * *" "Run monthly comprehensive 30-day audit per protocols/monthly-comprehensive-review-protocol.md"

echo "[skill 38] cron registration complete (4 jobs)"
