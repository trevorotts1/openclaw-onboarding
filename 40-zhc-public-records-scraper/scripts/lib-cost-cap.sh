#!/usr/bin/env bash
# lib-cost-cap.sh — Skill 40 cost estimate + per-day cap + per-target rate-limit
# guard. NO bulk op runs without an operator-confirmed cost estimate.
#
# Subcommands:
#   estimate <batch_size>           -> prints a JSON cost+time estimate (for bulk confirm)
#   under_daily_cap                 -> exit 0 if today's count < PR_DAILY_CAP, else 1
#   record_query                    -> increment today's per-day counter
#   rate_wait <target_ref>          -> take an atomic per-target reservation: sleep
#                                      the remaining interval WHILE HOLDING it and
#                                      stamp the timestamp at the request boundary.
#                                      Prints the seconds waited. The caller must
#                                      NOT sleep again.
#
# Caps (env-overridable):
#   PR_DAILY_CAP=200  PR_PER_TARGET_MIN_INTERVAL_S=5  PR_BULK_CONFIRM_THRESHOLD=25
#   PR_COST_PER_QUERY=0.00  PR_CACHE_TTL_DAYS=30
#
# State lives under the cache dir (per-day counter + per-target last-fetch ts).
# OS-aware. Uses jq when present; degrades gracefully.
#
# _cache_dir resolves MASTER_FILES_DIR from the env, then the persisted
# ~/.openclaw/.skill-40-master-files-dir selection written by
# 01-locate-master-files-folder.sh. It NEVER silently falls back to Downloads:
# an unresolved master-files dir means the per-day counter/rate-state would land
# in a fresh throwaway path, resetting the 200/day cap to zero — so it FAILS LOUD
# (nonzero + stderr) and the caller refuses rather than weakening the cap.

set -uo pipefail

PR_DAILY_CAP="${PR_DAILY_CAP:-200}"
PR_PER_TARGET_MIN_INTERVAL_S="${PR_PER_TARGET_MIN_INTERVAL_S:-5}"
PR_BULK_CONFIRM_THRESHOLD="${PR_BULK_CONFIRM_THRESHOLD:-25}"
PR_COST_PER_QUERY="${PR_COST_PER_QUERY:-0.00}"

_master_files_dir() {
  local mfd="${MASTER_FILES_DIR:-}"
  local state="${HOME:-/root}/.openclaw/.skill-40-master-files-dir"
  if [ -z "$mfd" ] && [ -f "$state" ]; then
    mfd="$(tr -d '[:space:]' < "$state" 2>/dev/null || true)"
  fi
  if [ -z "$mfd" ]; then
    echo "[skill 40][cost-cap] FATAL: MASTER_FILES_DIR unresolved — set MASTER_FILES_DIR or run scripts/01-locate-master-files-folder.sh (refusing to weaken the daily cap by writing state to a throwaway path)." >&2
    return 1
  fi
  printf '%s' "$mfd"
}

_cache_dir() {
  local mfd; mfd="$(_master_files_dir)" || return 1
  printf '%s/public-records-cache' "$mfd"
}

estimate() {
  local batch="${1:-0}"
  local cost secs over
  # cost = batch * PR_COST_PER_QUERY  (awk for float math; no bc dependency)
  cost="$(awk -v b="$batch" -v c="$PR_COST_PER_QUERY" 'BEGIN{printf "%.2f", b*c}')"
  secs="$(awk -v b="$batch" -v r="$PR_PER_TARGET_MIN_INTERVAL_S" 'BEGIN{printf "%d", b*r}')"
  # SK1-28: confirm_required is gated on BATCH SIZE, not est_cost — est_cost is
  # $0.00 for free public portals (PR_COST_PER_QUERY defaults to 0.00) and is
  # informational only. A paid vendor should set PR_COST_PER_QUERY to a real price.
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

_counter_file() { local d; d="$(_cache_dir)" || return 1; printf '%s/.daily-count-%s' "$d" "$(_today)"; }

# FAIL CLOSED: if the master-files dir is unresolved, treat the cap as reached
# (return nonzero) rather than comparing against a phantom 0-count file that
# would let the cap be bypassed forever.
under_daily_cap() {
  local cf n; cf="$(_counter_file)" || {
    echo "[skill 40][cost-cap] cap state unresolved — failing CLOSED (treating as over cap)." >&2; return 1; }
  n=0; [ -f "$cf" ] && n="$(tr -d '[:space:]' < "$cf" 2>/dev/null || echo 0)"
  [ "${n:-0}" -lt "$PR_DAILY_CAP" ]
}

record_query() {
  local cf n d; cf="$(_counter_file)" || return 1
  d="$(_cache_dir)" || return 1
  mkdir -p "$d" 2>/dev/null || true
  n=0; [ -f "$cf" ] && n="$(tr -d '[:space:]' < "$cf" 2>/dev/null || echo 0)"
  printf '%s\n' "$(( ${n:-0} + 1 ))" > "$cf"
}

# rate_wait <target_ref> — ATOMIC per-target reservation (SK1-30 / T2-33).
#
# The old shape computed the remaining delay, PRINTED it, stamped the timestamp
# immediately, and left the sleeping to the caller. The recorded time was
# therefore the time the delay was COMPUTED, not the time the request was made,
# so the next computation measured from the wrong origin: after one waited
# request, the following request measured its gap from the previous
# COMPUTATION and could fire with zero spacing. The audit log recorded a
# compliant wait for a non-compliant request rate — a terms-of-service exposure
# on a scraping skill.
#
# The reservation is now one indivisible step:
#   1. take a per-target lock (mkdir is atomic on every POSIX filesystem),
#   2. compute the delay from the last ACTUAL request time,
#   3. sleep the remainder WHILE HOLDING the reservation (so a concurrent
#      caller queues behind it instead of racing through),
#   4. stamp the timestamp at the REQUEST BOUNDARY — the instant before this
#      function returns and the caller issues the request,
#   5. release the lock.
# It prints the seconds actually waited, for the rate_limit_wait audit event.
# The caller must NOT sleep again.
#
# Lock staleness: a lock older than (interval + 60)s is treated as abandoned
# (a killed process) and reclaimed, so a crash can never wedge a target.
rate_wait() {
  local target="${1:-default}" lf lockdir last now diff d safe waited=0 tries=0 max_tries lock_age
  d="$(_cache_dir)" || return 1
  mkdir -p "$d" 2>/dev/null || true
  safe="$(printf '%s' "$target" | tr -c 'A-Za-z0-9_-' '_')"
  lf="$d/.last-fetch-$safe"
  lockdir="$d/.rate-lock-$safe"
  max_tries=$(( PR_PER_TARGET_MIN_INTERVAL_S * 4 + 60 ))

  while ! mkdir "$lockdir" 2>/dev/null; do
    lock_age=0
    if [ -d "$lockdir" ]; then
      case "$(uname -s)" in
        Darwin) lock_age=$(( $(date +%s) - $(stat -f %m "$lockdir" 2>/dev/null || date +%s) )) ;;
        *)      lock_age=$(( $(date +%s) - $(stat -c %Y "$lockdir" 2>/dev/null || date +%s) )) ;;
      esac
    fi
    if [ "$lock_age" -gt $(( PR_PER_TARGET_MIN_INTERVAL_S + 60 )) ]; then
      echo "[skill 40][cost-cap] reclaiming a stale rate reservation for $target (age ${lock_age}s)" >&2
      rmdir "$lockdir" 2>/dev/null || true
      continue
    fi
    tries=$(( tries + 1 ))
    if [ "$tries" -ge "$max_tries" ]; then
      echo "[skill 40][cost-cap] could not acquire the rate reservation for $target within ${max_tries}s — refusing the request rather than bypassing the interval." >&2
      return 1
    fi
    sleep 1
  done

  now="$(date +%s)"
  last=0; [ -f "$lf" ] && last="$(tr -d '[:space:]' < "$lf" 2>/dev/null || echo 0)"
  diff=$(( now - ${last:-0} ))
  if [ "${last:-0}" -gt 0 ] && [ "$diff" -lt "$PR_PER_TARGET_MIN_INTERVAL_S" ]; then
    waited=$(( PR_PER_TARGET_MIN_INTERVAL_S - diff ))
    sleep "$waited"
  fi
  # REQUEST BOUNDARY: stamp now, release, return — the caller issues the request
  # on the very next statement.
  printf '%s\n' "$(date +%s)" > "$lf"
  rmdir "$lockdir" 2>/dev/null || true
  echo "$waited"
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
