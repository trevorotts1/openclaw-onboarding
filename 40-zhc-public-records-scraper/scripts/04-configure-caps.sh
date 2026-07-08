#!/usr/bin/env bash
# 04-configure-caps.sh — Skill 40
# Records the cost/rate/cache caps (env-overridable) into a non-secret config in
# the master files, and prints an honest summary. Idempotent.

set -uo pipefail
P="[skill 40][caps]"

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-40-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"
CFG="$MFD/public-records-cache/caps.json"
mkdir -p "$(dirname "$CFG")" 2>/dev/null || true

PR_DAILY_CAP="${PR_DAILY_CAP:-200}"
PR_PER_TARGET_MIN_INTERVAL_S="${PR_PER_TARGET_MIN_INTERVAL_S:-5}"
PR_BULK_CONFIRM_THRESHOLD="${PR_BULK_CONFIRM_THRESHOLD:-25}"
PR_COST_PER_QUERY="${PR_COST_PER_QUERY:-0.00}"
PR_CACHE_TTL_DAYS="${PR_CACHE_TTL_DAYS:-30}"

if command -v jq >/dev/null 2>&1; then
  jq -cn \
    --argjson daily "$PR_DAILY_CAP" \
    --argjson interval "$PR_PER_TARGET_MIN_INTERVAL_S" \
    --argjson bulk "$PR_BULK_CONFIRM_THRESHOLD" \
    --arg cost "$PR_COST_PER_QUERY" \
    --argjson ttl "$PR_CACHE_TTL_DAYS" \
    '{daily_cap:$daily, per_target_min_interval_s:$interval, bulk_confirm_threshold:$bulk, cost_per_query:($cost|tonumber), cache_ttl_days:$ttl}' \
    > "$CFG"
else
  printf '{"daily_cap":%s,"per_target_min_interval_s":%s,"bulk_confirm_threshold":%s,"cost_per_query":%s,"cache_ttl_days":%s}\n' \
    "$PR_DAILY_CAP" "$PR_PER_TARGET_MIN_INTERVAL_S" "$PR_BULK_CONFIRM_THRESHOLD" "$PR_COST_PER_QUERY" "$PR_CACHE_TTL_DAYS" > "$CFG"
fi

echo "$P caps written → $CFG"
echo "$P    daily cap                 : $PR_DAILY_CAP queries/day"
echo "$P    per-target rate limit     : 1 request / ${PR_PER_TARGET_MIN_INTERVAL_S}s"
echo "$P    bulk confirm threshold    : $PR_BULK_CONFIRM_THRESHOLD queries (above this => cost estimate + operator confirm)"
echo "$P    est. cost per query       : \$$PR_COST_PER_QUERY  (public portals are free; the bulk-confirm gate is batch-size-based — set this only for a PAID vendor)"
echo "$P    cache TTL                 : $PR_CACHE_TTL_DAYS days"
echo "$P Override any cap via its env var (PR_DAILY_CAP, PR_PER_TARGET_MIN_INTERVAL_S, PR_BULK_CONFIRM_THRESHOLD, PR_COST_PER_QUERY, PR_CACHE_TTL_DAYS) and re-run."
exit 0
