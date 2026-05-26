#!/usr/bin/env bash
# generate-celebration-video.sh — KIE.AI Veo 3.1 call (veo3_fast default).
#
# Fills templates/veo-prompt.txt with company-specific placeholders, submits to
# the VEO-specific endpoint, polls /api/v1/veo/record-info, writes
# celebrationVideoUrl to state.
#
# v10.14.2 / v10.15.2 fixes:
#   - duration is now parameterized via ZHC_VIDEO_DURATION (default 8) and
#     snapped to a Veo-valid value (4/6/8). Invalid inputs fall back to 8.
#   - polling endpoint corrected to /api/v1/veo/record-info with
#     successFlag-based completion detection.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[veo] no OpenClaw root" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$SKILL_DIR/templates/veo-prompt.txt"
STEP_LABEL="celebration-video"

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2"
}
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }

COMPANY_NAME=$(state_get '.companyName'); [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="Your Company"
OWNER_NAME=$(state_get '.ownerName'); [[ -z "$OWNER_NAME" ]] && OWNER_NAME="the Owner"
AGENT_NAME=$(state_get '.agentName'); [[ -z "$AGENT_NAME" ]] && AGENT_NAME="the CEO Agent"
INDUSTRY=$(state_get '.industry'); [[ -z "$INDUSTRY" ]] && INDUSTRY="modern business"

if [[ ! -f "$TEMPLATE" ]]; then
  log "ERROR" "veo prompt template missing: $TEMPLATE"
  exit 1
fi

PROMPT=$(cat "$TEMPLATE" \
  | sed "s|{{COMPANY_NAME}}|${COMPANY_NAME}|g" \
  | sed "s|{{OWNER_NAME}}|${OWNER_NAME}|g" \
  | sed "s|{{AGENT_NAME}}|${AGENT_NAME}|g" \
  | sed "s|{{INDUSTRY}}|${INDUSTRY}|g")

MODEL="${ZHC_VIDEO_MODEL:-veo3_fast}"

# ---- duration: snap to a Veo-valid value (4/6/8). Default 8. ----
DURATION_INPUT="${ZHC_VIDEO_DURATION:-8}"
case "$DURATION_INPUT" in
  4|6|8) DURATION="$DURATION_INPUT" ;;
  *)
    log "WARN" "ZHC_VIDEO_DURATION='$DURATION_INPUT' is not a valid Veo duration (4/6/8); falling back to 8"
    DURATION="8"
    ;;
esac

submit_veo() {
  local body
  body=$(jq -n \
    --arg model "$MODEL" \
    --arg prompt "$PROMPT" \
    --argjson duration "$DURATION" \
    '{model: $model, prompt: $prompt, aspect_ratio: "9:16", duration: $duration, generate_audio: true}')
  curl -sS --fail-with-body -X POST "https://api.kie.ai/api/v1/veo/generate" \
    -H "Authorization: Bearer $KIE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$body"
}

poll_veo() {
  local task_id="$1"
  local elapsed=0
  local wait_sec
  while (( elapsed < 900 )); do  # videos can take 10+ min
    local resp http_code
    # capture body + status code so 4xx/5xx are handled, not silently retried
    resp=$(curl -sS -w '\n__HTTP_CODE__%{http_code}' \
      "https://api.kie.ai/api/v1/veo/record-info?taskId=$task_id" \
      -H "Authorization: Bearer $KIE_API_KEY" 2>/dev/null)
    http_code=$(printf '%s' "$resp" | awk -F'__HTTP_CODE__' 'END{print $2}')
    resp=$(printf '%s' "$resp" | sed 's/__HTTP_CODE__[0-9]*$//')

    if [[ -n "$http_code" && "$http_code" =~ ^[45] ]]; then
      log "ERROR" "VEO poll HTTP $http_code for $task_id: $(echo "$resp" | head -c 200)"
      # transient 5xx: retry; terminal 4xx: bail
      if [[ "$http_code" =~ ^4 ]]; then
        return 1
      fi
    fi

    # successFlag = 1 (numeric or string) means done; -1 means failed; 0 means in-progress.
    local success_flag
    success_flag=$(echo "$resp" | jq -r '.data.successFlag // empty' 2>/dev/null)
    case "$success_flag" in
      1|"1")
        echo "$resp" | jq -r '.data.response.resultUrls[0] // .data.response.videoUrl // .data.resultJson' 2>/dev/null \
          | { read first; if [[ "$first" == \{* ]]; then echo "$first" | jq -r '.resultUrls[0] // .videoUrl // .url // empty'; else echo "$first"; fi; }
        return 0
        ;;
      -1|"-1")
        local msg
        msg=$(echo "$resp" | jq -r '.data.errorMessage // .data.failMsg // .msg // "unknown"')
        log "ERROR" "VEO job $task_id failed: $msg"
        return 1
        ;;
    esac

    if (( elapsed < 60 )); then wait_sec=5
    elif (( elapsed < 300 )); then wait_sec=15
    else wait_sec=30
    fi
    sleep "$wait_sec"
    elapsed=$((elapsed + wait_sec))
  done
  log "ERROR" "VEO job $task_id timed out after ${elapsed}s"
  return 1
}

attempt=0
result_url=""
while (( attempt < 2 )); do  # videos are expensive; only 2 retries
  attempt=$((attempt + 1))
  log "INFO" "attempt $attempt/2: submitting VEO job model=$MODEL duration=${DURATION}s"
  submit_resp=$(submit_veo || true)
  task_id=$(echo "$submit_resp" | jq -r '.data.taskId // .taskId // empty' 2>/dev/null)
  if [[ -z "$task_id" ]]; then
    log "WARN" "attempt $attempt: submit failed, response: $(echo "$submit_resp" | head -c 200)"
    sleep $((4 ** attempt))
    continue
  fi
  log "INFO" "attempt $attempt: submitted taskId=$task_id; polling /veo/record-info..."
  if result_url=$(poll_veo "$task_id"); then
    if [[ -n "$result_url" && "$result_url" != "null" ]]; then
      log "INFO" "attempt $attempt: success url=$result_url"
      break
    fi
  fi
  result_url=""
  sleep $((4 ** attempt))
done

if [[ -z "$result_url" ]]; then
  log "ERROR" "all 2 attempts exhausted; no celebration video produced"
  exit 1
fi

state_set ".celebrationVideoUrl = \"$result_url\""
log "INFO" "wrote celebrationVideoUrl=$result_url to state"
exit 0
