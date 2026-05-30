#!/usr/bin/env bash
# lib-cost-cap.sh — Skill 40 cost estimate + per-day cap + per-target rate-limit
# guard. NO bulk op runs without an operator-confirmed cost estimate.
#
# Subcommands:
#   estimate <batch_size>           -> prints a JSON cost+time estimate (for bulk confirm)
#   under_daily_cap                 -> exit 0 if today's count < PR_DAILY_CAP, else 1
#   record_query                    -> increment today's per-day counter
#   rate_wait <target_ref>          -> sleep so the per-target min interval is honored
#
# Caps (env-overridable):
#   PR_DAILY_CAP=200  PR_PER_TARGET_MIN_INTERVAL_S=5  PR_BULK_CONFIRM_THRESHOLD=25
#   PR_COST_PER_QUERY=0.00  PR_CACHE_TTL_DAYS=30
#
# State lives under the cache dir (per-day counter + per-target last-fetch ts).
# OS-aware. Uses jq when present; degrades gracefully.

set -uo pipefail

PR_DAILY_CAP="${PR_DAILY_CAP:-200}"
PR_PER_TARGET_MIN_INTERVAL_S="${PR_PER_TARGET_MIN_INTERVAL_S:-5}"
PR_BULK_CONFIRM_THRESHOLD="${PR_BULK_CONFIRM_THRESHOLD:-25}"
PR_COST_PER_QUERY="${PR_COST_PER_QUERY:-0.00}"

_cache_dir() {
  local mfd="${MASTER_FILES_DIR:-}"
  if [ -z "$mfd" ]; then case "$(uname -s)" in Darwin) mfd="$HOME/Downloads" ;; *) mfd="/data" ;; esac; fi
  printf '%s/public-records-cache' "$mfd"
}

estimate() {
  local batch="${1:-0}"
  local cost secs over
  # cost = batch * PR_COST_PER_QUERY  (awk for float math; no bc dependency)
  cost="$(awk -v b="$batch" -v c="$PR_COST_PER_QUERY" 'BEGIN{printf "%.2f", b*c}')"
  secs="$(awk -v b="$batch" -v r="$PR_PER_TARGET_MIN_INTERVAL_S" 'BEGIN{printf "%d", b*r}')"
  over="false"; [ "$batch" -gt "$PR_BULK_CONFIRM_THRESHOLD" ] 2>/dev/null && over="true"
  if command -v jq >/dev/null 2>&1; then
    jq -cn --argjson b "$batch" --arg cost "$cost" --argjson secs "$secs" \
      --argjson thr "$PR_BULK_CONFIRM_THRESHOLD" --argjson over "$over" \
      '{batch_size:$b, est_cost:($cost|tonumber), est_seconds:$secs, confirm_required:$over, threshold:$thr}'
  else
    printf '{"batch_size":%s,"est_cost":%s,"est_seconds":%s,"confirm_required":%s,"threshold":%s}\n' \
      "$batch" "$cost" "$secs" "$over" "$PR_BULK_CONFIRM_THRESHOLD"
  fi
}

_today() { date -u +%Y-%m-%d; }

_counter_file() { printf '%s/.daily-count-%s' "$(_cache_dir)" "$(_today)"; }

under_daily_cap() {
  local cf n; cf="$(_counter_file)"
  n=0; [ -f "$cf" ] && n="$(tr -d '[:space:]' < "$cf" 2>/dev/null || echo 0)"
  [ "${n:-0}" -lt "$PR_DAILY_CAP" ]
}

record_query() {
  local cf n; cf="$(_counter_file)"
  mkdir -p "$(_cache_dir)" 2>/dev/null || true
  n=0; [ -f "$cf" ] && n="$(tr -d '[:space:]' < "$cf" 2>/dev/null || echo 0)"
  printf '%s\n' "$(( ${n:-0} + 1 ))" > "$cf"
}

rate_wait() {
  local target="${1:-default}" lf last now diff
  lf="$(_cache_dir)/.last-fetch-$(printf '%s' "$target" | tr -c 'A-Za-z0-9_-' '_')"
  mkdir -p "$(_cache_dir)" 2>/dev/null || true
  now="$(date +%s)"
  last=0; [ -f "$lf" ] && last="$(tr -d '[:space:]' < "$lf" 2>/dev/null || echo 0)"
  diff=$(( now - ${last:-0} ))
  if [ "$diff" -lt "$PR_PER_TARGET_MIN_INTERVAL_S" ] && [ "${last:-0}" -gt 0 ]; then
    local wait=$(( PR_PER_TARGET_MIN_INTERVAL_S - diff ))
    echo "$wait"   # caller logs rate_limit_wait + sleeps (kept side-effect-light here)
  else
    echo "0"
  fi
  printf '%s\n' "$(date +%s)" > "$lf"
}

if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  cmd="${1:-}"; shift || true
  case "$cmd" in
    estimate)        estimate "$@" ;;
    under_daily_cap) under_daily_cap; exit $? ;;
    record_query)    record_query ;;
    rate_wait)       rate_wait "$@" ;;
    -h|--help)       sed -n '1,22p' "$0" ;;
    *) echo "usage: $0 {estimate <n>|under_daily_cap|record_query|rate_wait <target>}" >&2; exit 2 ;;
  esac
fi
