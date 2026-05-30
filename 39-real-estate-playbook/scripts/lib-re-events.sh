#!/usr/bin/env bash
# lib-re-events.sh — Skill 39 append-one-line helper for the F52 master-files
# event contract: <MASTER_FILES_DIR>/real-estate-events.jsonl
#
# Usage (sourced or called):
#   bash lib-re-events.sh re_event <event-type> '<json-payload-object>'
#   # or, sourced:  source lib-re-events.sh; re_event geocode '{"matched":true}'
#
# Every event line gets the common fields (ts, skill, event) merged with the
# caller-supplied payload. The caller is responsible for keeping payloads
# PII-free (field NAMES + counts + an opaque lead_ref, never raw PII) — see
# INSTRUCTIONS.md "real-estate-events.jsonl schema".
#
# Idempotent in the sense that it only ever APPENDS; it never rewrites history.
# OS-aware (Darwin + Linux). Requires jq.

set -uo pipefail

SKILL_NAME="39-real-estate-playbook"

re_events_log_path() {
  local mfd="${MASTER_FILES_DIR:-}"
  if [ -z "$mfd" ]; then
    case "$(uname -s)" in
      Darwin) mfd="$HOME/Downloads" ;;
      *)      mfd="/data" ;;
    esac
  fi
  printf '%s/real-estate-events.jsonl' "$mfd"
}

re_event() {
  local etype="${1:-}"
  local payload="${2:-}"
  [ -n "$payload" ] || payload='{}'
  if [ -z "$etype" ]; then
    echo "re_event: missing event type" >&2
    return 2
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "re_event: jq not found on PATH — cannot append event" >&2
    return 2
  fi
  # Validate the caller payload is a JSON object (fail closed; never write junk).
  if ! printf '%s' "$payload" | jq -e 'type == "object"' >/dev/null 2>&1; then
    echo "re_event: payload is not a JSON object: $payload" >&2
    return 2
  fi
  local ts log line
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  log="$(re_events_log_path)"
  mkdir -p "$(dirname "$log")" 2>/dev/null || true
  # Merge common fields + payload. Common fields win on key collision so the
  # contract (ts/skill/event) can never be spoofed by a caller payload.
  line="$(jq -cn \
    --arg ts "$ts" \
    --arg skill "$SKILL_NAME" \
    --arg event "$etype" \
    --argjson payload "$payload" \
    '$payload + {ts:$ts, skill:$skill, event:$event}')" || {
      echo "re_event: jq merge failed" >&2; return 2; }
  printf '%s\n' "$line" >> "$log" || {
    echo "re_event: failed to append to $log" >&2; return 2; }
  return 0
}

# If invoked directly (not sourced), dispatch the first arg.
if [ "${BASH_SOURCE[0]:-}" = "${0:-}" ]; then
  case "${1:-}" in
    re_event) shift; re_event "$@" ;;
    path)     re_events_log_path ;;
    -h|--help) sed -n '1,20p' "$0" ;;
    *) echo "usage: $0 {re_event <type> <json> | path}" >&2; exit 2 ;;
  esac
fi
