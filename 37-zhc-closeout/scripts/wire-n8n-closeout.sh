#!/usr/bin/env bash
# wire-n8n-closeout.sh — PRD-2.8: n8n wire-up step for the ZHC closeout pipeline.
#
# Notifies the client's n8n instance (via webhook) that the ZHC build + closeout
# is complete, handing off: company slug, agent name, Command Center URL, and
# the closeout artifact URLs. n8n then drives any post-build automations the
# client has (e.g. GHL CRM update, Slack channel creation, calendar block).
#
# SKIP CONDITIONS (graceful, never blocks closeout):
#   • N8N_WEBHOOK_URL env var not set AND ZHC_SKIP_N8N not set  → warn + skip
#   • ZHC_SKIP_N8N=1                                             → explicit skip
#   • n8nStatus already "wired" in state                        → idempotent skip
#
# The step writes n8nStatus = "wired"|"skipped"|"failed" + n8nUrl to state.
# It does NOT fail the overall closeout on n8n errors (n8n is optional).
#
# EXIT CODES:
#   0  → wired or skipped (non-fatal outcomes)
#   1  → hard wire failure after retries (only when N8N_WEBHOOK_URL is set)
#
# PRD-2.8 / v11.10.0

set -u

# ---- platform detection ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[wire-n8n] no OpenClaw root found; aborting" >&2
  exit 1
fi

STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
LOG_FILE="${ZHC_LOG_FILE:-$OC_ROOT/workspace/.zhc-closeout.log}"

log() {
  printf '%s [%-5s] step=n8n %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" | tee -a "$LOG_FILE"
}

state_get() {
  jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null
}

state_set() {
  local tmp
  tmp=$(mktemp)
  if jq "$1" "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "state_set failed for expr: $1"
    return 1
  fi
}

# ---- guard: jq required ----
command -v jq >/dev/null 2>&1 || { log "ERROR" "jq not found -- aborting"; exit 1; }

# ---- idempotency ----
n8n_status=$(state_get '.n8nStatus')
if [[ "$n8n_status" == "wired" ]]; then
  log "INFO" "n8nStatus=wired already -- skipping (idempotent)"
  exit 0
fi

# ---- explicit skip ----
if [[ "${ZHC_SKIP_N8N:-}" == "1" ]]; then
  log "INFO" "ZHC_SKIP_N8N=1 -- explicit skip"
  state_set '.n8nStatus = "skipped" | .closeoutDeliverables.n8nWired = "skipped"' || true
  exit 0
fi

# ---- no webhook → warn + skip ----
N8N_WEBHOOK_URL="${N8N_WEBHOOK_URL:-}"
if [[ -z "$N8N_WEBHOOK_URL" ]]; then
  # Try to resolve from openclaw config
  if command -v openclaw >/dev/null 2>&1; then
    N8N_WEBHOOK_URL="$(openclaw config get env.vars.N8N_WEBHOOK_URL 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$N8N_WEBHOOK_URL" in
      ""|*"not found"*|*"Error"*) N8N_WEBHOOK_URL="" ;;
    esac
  fi
fi

if [[ -z "$N8N_WEBHOOK_URL" ]]; then
  log "INFO" "N8N_WEBHOOK_URL not set -- skipping n8n wire-up (client has no n8n integration)"
  state_set '.n8nStatus = "skipped" | .closeoutDeliverables.n8nWired = "skipped"' || true
  exit 0
fi

# ---- read state fields ----
company_name=$(state_get '.companyName // "Unknown Company"')
company_slug=$(state_get '.companySlug // ""')
if [[ -z "$company_slug" ]]; then
  company_slug=$(printf '%s' "$company_name" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/--*/-/g; s/^-//; s/-$//')
fi
owner_name=$(state_get '.ownerName // "Owner"')
agent_name=$(state_get '.agentName // "CEO"')
cc_url=$(state_get '.commandCenterUrl // ""')
infographic1_url=$(state_get '.infographic1Url // ""')
infographic2_url=$(state_get '.infographic2Url // ""')
celebration_video_url=$(state_get '.ghlVideoPublicUrl // .celebrationVideoUrl // ""')
notion_url=$(state_get '.notionRootPageUrl // ""')
owner_chat=$(state_get '.ownerChat // ""')

# ---- build payload ----
payload=$(jq -n \
  --arg event         "zhc_closeout_complete" \
  --arg companySlug   "$company_slug" \
  --arg companyName   "$company_name" \
  --arg ownerName     "$owner_name" \
  --arg agentName     "$agent_name" \
  --arg ccUrl         "$cc_url" \
  --arg infographic1  "$infographic1_url" \
  --arg infographic2  "$infographic2_url" \
  --arg videoUrl      "$celebration_video_url" \
  --arg notionUrl     "$notion_url" \
  --arg ownerChat     "$owner_chat" \
  --arg firedAt       "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    event:          $event,
    companySlug:    $companySlug,
    companyName:    $companyName,
    ownerName:      $ownerName,
    agentName:      $agentName,
    commandCenterUrl: $ccUrl,
    infographic1Url:  $infographic1,
    infographic2Url:  $infographic2,
    celebrationVideoUrl: $videoUrl,
    notionRootPageUrl:   $notionUrl,
    ownerTelegramChat:   $ownerChat,
    firedAt:             $firedAt
  }')

log "INFO" "POSTing closeout event to n8n webhook (company=$company_slug)"

# ---- retry loop (3 attempts) ----
max_attempts=3
attempt=0
http_rc=0
while (( attempt < max_attempts )); do
  attempt=$((attempt + 1))
  log "INFO" "n8n webhook attempt $attempt/$max_attempts"

  http_response=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time 30 \
    -X POST "$N8N_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>>"$LOG_FILE")

  http_rc=$?
  if [[ "$http_rc" -eq 0 && "$http_response" =~ ^2 ]]; then
    log "INFO" "n8n webhook accepted (HTTP $http_response)"
    state_set \
      ".n8nStatus = \"wired\" | .n8nUrl = \"$N8N_WEBHOOK_URL\" | .closeoutDeliverables.n8nWired = true" || true
    exit 0
  fi

  log "WARN" "n8n webhook attempt $attempt: curl_rc=$http_rc http=$http_response"
  sleep $(( 2 ** attempt ))
done

# ---- exhausted ----
log "ERROR" "n8n webhook FAILED after $max_attempts attempts (last http=$http_response). Marking n8nStatus=failed (non-blocking -- closeout continues)."
state_set ".n8nStatus = \"failed\" | .closeoutDeliverables.n8nWired = false" || true
# Non-blocking: n8n is optional. Run-closeout.sh treats a soft-failed n8n step
# the same as a failed video -- partial, not a hard closeout failure.
exit 1
