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

# SK1-21: CODED fair-housing gate (fail-closed). Fair housing was previously
# enforced ONLY by LLM prose (references/fair-housing-guardrails.md). Routing and
# qualification must NEVER record or route on a protected characteristic, so any
# event payload carrying a protected-class field is a violation and is REFUSED at
# the write chokepoint below — no protected attribute ever reaches the audit log
# or a downstream routing decision. Covers the federal Fair Housing Act classes
# plus common state/local additions (age, marital status, source of income,
# military/veteran status). qc-fair-housing.sh exercises this denylist.
FAIR_HOUSING_DENY_KEYS='^(race|ethnicity|color|religion|religious|creed|national_origin|nationality|ancestry|sex|gender|gender_identity|sexual_orientation|orientation|familial_status|family_status|children|num_children|disability|handicap|age|marital_status|source_of_income|section_?8|housing_voucher|voucher|veteran_status|military_status|immigration_status)$'

# fair_housing_offending_keys <payload> -> prints any protected-class keys found
# in the JSON payload (recursively), one per line; empty output == clean.
fair_housing_offending_keys() {
  local payload="${1:-}"
  command -v jq >/dev/null 2>&1 || return 0
  printf '%s' "$payload" \
    | jq -r 'try ([.. | objects | keys[]] | .[]) catch empty' 2>/dev/null \
    | tr '[:upper:]' '[:lower:]' \
    | grep -E "$FAIR_HOUSING_DENY_KEYS" || true
}

# Resolve MASTER_FILES_DIR from the SAME persisted single-source-of-truth that
# 01-locate-master-files-folder.sh writes — NEVER a caller-env-dependent
# $HOME/Downloads (or /data) fallback. That fallback was the Skill-23-class
# split-brain: a test run (or a caller with a different HOME) would write the
# event log to a DIFFERENT file than the live agent, silently splitting the
# operator's ground-truth audit log. Resolution order:
#   1. An explicit MASTER_FILES_DIR env var (must be an existing dir).
#   2. The persisted selection file written at install (own Skill-39 file first,
#      then Skill 38's — the shared source of truth), under either OS home root.
# If none resolves, we FAIL LOUDLY (return 1) rather than guessing a path.
re_events_master_dir() {
  local mfd="${MASTER_FILES_DIR:-}"
  if [ -n "$mfd" ] && [ -d "$mfd" ]; then
    printf '%s' "$mfd"; return 0
  fi
  local root cand d
  for root in "$HOME/.openclaw" "/data/.openclaw"; do
    for cand in "$root/.skill-39-master-files-dir" "$root/.skill-38-master-files-dir"; do
      [ -f "$cand" ] || continue
      d="$(tr -d '[:space:]' < "$cand" 2>/dev/null || true)"
      if [ -n "$d" ] && [ -d "$d" ]; then
        printf '%s' "$d"; return 0
      fi
    done
  done
  return 1
}

re_events_log_path() {
  local mfd
  if ! mfd="$(re_events_master_dir)"; then
    echo "re_event: MASTER_FILES_DIR unresolved — set MASTER_FILES_DIR or run 01-locate-master-files-folder.sh first (refusing to fall back to Downloads / a caller-split path)." >&2
    return 1
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
  # SK1-21: fair-housing chokepoint — REFUSE (fail-closed) any event that carries
  # a protected-class field. Routing/qualification must never record or route on
  # a protected characteristic; this stops it reaching the audit log.
  local _fh_hits
  _fh_hits="$(fair_housing_offending_keys "$payload")"
  if [ -n "$_fh_hits" ]; then
    echo "re_event: REFUSED (fair-housing) — payload contains protected-class field(s): $(printf '%s' "$_fh_hits" | paste -sd, - 2>/dev/null | sed 's/,$//'). Never record or route on a protected characteristic (references/fair-housing-guardrails.md)." >&2
    return 3
  fi
  local ts log line
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # Loud fail (never a Downloads fallback) if MASTER_FILES_DIR cannot be resolved.
  log="$(re_events_log_path)" || return 2
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
