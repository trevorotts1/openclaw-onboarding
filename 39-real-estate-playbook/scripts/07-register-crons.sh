#!/usr/bin/env bash
# 07-register-crons.sh — Skill 39
# Registers the two RE maintenance crons via `openclaw cron add` (the supported
# path on 2026.5.x — cron.jobs JSON does NOT validate). Idempotent: skips a cron
# whose name already exists. If the openclaw CLI is unavailable, prints the exact
# commands for the operator to run and exits 0 (non-fatal).
#
#   re-open-house-followup-scan : daily 18:00  — open-house follow-up sweep
#   re-post-close-anniversary   : daily 09:00  — post-close anniversary / sphere nurture

set -uo pipefail
P="[skill 39][crons]"

declare -a CRON_NAMES=( "re-open-house-followup-scan" "re-post-close-anniversary" )
declare -a CRON_SCHED=( "0 18 * * *"                  "0 9 * * *" )
declare -a CRON_DESC=(
  "Skill 39: daily open-house follow-up sweep (open-house-automation-protocol.md)"
  "Skill 39: daily post-close anniversary + sphere reactivation nurture scan"
)

if ! command -v openclaw >/dev/null 2>&1; then
  echo "$P openclaw CLI not on PATH — register these manually (non-fatal):"
  for i in "${!CRON_NAMES[@]}"; do
    echo "$P    openclaw cron add --name \"${CRON_NAMES[$i]}\" --schedule \"${CRON_SCHED[$i]}\" --description \"${CRON_DESC[$i]}\""
  done
  exit 0
fi

EXISTING="$(openclaw cron list 2>/dev/null || true)"
for i in "${!CRON_NAMES[@]}"; do
  name="${CRON_NAMES[$i]}"
  if printf '%s' "$EXISTING" | grep -qF "$name"; then
    echo "$P cron '$name' already registered — skipping"
    continue
  fi
  if openclaw cron add --name "$name" --schedule "${CRON_SCHED[$i]}" --description "${CRON_DESC[$i]}" >/dev/null 2>&1; then
    echo "$P registered cron '$name' (${CRON_SCHED[$i]})"
  else
    echo "$P WARN: could not register '$name' — run manually:"
    echo "$P    openclaw cron add --name \"$name\" --schedule \"${CRON_SCHED[$i]}\" --description \"${CRON_DESC[$i]}\""
  fi
done
exit 0
