#!/usr/bin/env bash
# lib-pr-events.sh — Skill 40 append-one-line helper for the F52 master-files
# event contract: <MASTER_FILES_DIR>/public-records-queries.jsonl
#
# Usage (sourced or called):
#   bash lib-pr-events.sh pr_event <event-type> '<json-payload-object>'
#   source lib-pr-events.sh; pr_event tier_decision '{"tier":"tier1"}'
#
# Every line gets the common fields (ts, skill, event) merged with the payload.
# The caller keeps payloads PII-free (record TYPES + counts + opaque handles,
# never raw record contents) — see INSTRUCTIONS.md schema.
# APPEND-only. OS-aware. Requires jq.

set -uo pipefail
SKILL_NAME="40-zhc-public-records-scraper"

pr_events_log_path() {
  # SK1-27: resolve MASTER_FILES_DIR the SAME way lib-records.sh / lib-cost-cap.sh
  # do — env first, then the persisted selection written by
  # 01-locate-master-files-folder.sh — and FAIL LOUD if unresolved. The old
  # $HOME/Downloads (Darwin) // /data fallback split the events log away from the
  # cache + per-day counter (which use the persisted selection and never fall
  # back), silently fracturing the operator's audit trail across two directories.
  local mfd="${MASTER_FILES_DIR:-}"
  if [ -z "$mfd" ]; then
    local state="${HOME:-/root}/.openclaw/.skill-40-master-files-dir"
    [ -f "$state" ] && mfd="$(tr -d '[:space:]' < "$state" 2>/dev/null || true)"
  fi
  if [ -z "$mfd" ]; then
    echo "[skill 40][pr-events] FATAL: MASTER_FILES_DIR unresolved — set MASTER_FILES_DIR or run scripts/01-locate-master-files-folder.sh (refusing a Downloads fallback that would split the events log from the cache/counter)." >&2
    return 1
  fi
  printf '%s/public-records-queries.jsonl' "$mfd"
}

pr_event() {
  local etype="${1:-}"
  local payload="${2:-}"
  [ -n "$payload" ] || payload='{}'
  if [ -z "$etype" ]; then echo "pr_event: missing event type" >&2; return 2; fi
  if ! command -v jq >/dev/null 2>&1; then echo "pr_event: jq not found" >&2; return 2; fi
  if ! printf '%s' "$payload" | jq -e 'type == "object"' >/dev/null 2>&1; then
    echo "pr_event: payload is not a JSON object: $payload" >&2; return 2
  fi
  local ts log line
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # SK1-27: no Downloads fallback — if the master-files dir is unresolved, skip
  # the write (the caller _emit is fail-soft) rather than split the audit trail.
  log="$(pr_events_log_path)" || { echo "pr_event: MASTER_FILES_DIR unresolved — event not written" >&2; return 2; }
  mkdir -p "$(dirname "$log")" 2>/dev/null || true
  line="$(jq -cn \
    --arg ts "$ts" --arg skill "$SKILL_NAME" --arg event "$etype" --argjson payload "$payload" \
    '$payload + {ts:$ts, skill:$skill, event:$event}')" || { echo "pr_event: jq merge failed" >&2; return 2; }
  printf '%s\n' "$line" >> "$log" || { echo "pr_event: append failed to $log" >&2; return 2; }
  return 0
}

if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  case "${1:-}" in
    pr_event) shift; pr_event "$@" ;;
    path)     pr_events_log_path ;;
    -h|--help) sed -n '1,18p' "$0" ;;
    *) echo "usage: $0 {pr_event <type> <json> | path}" >&2; exit 2 ;;
  esac
fi
