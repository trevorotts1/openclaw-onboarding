#!/usr/bin/env bash
# generate-infographics.sh - KIE.AI gpt-image-2 call.
#
# Usage: generate-infographics.sh structure|workflow
#
# Reads .workforce-build-state.json + workforce-interview-answers.md for
# placeholders, fills the prompt template, submits to KIE.AI, polls for
# completion, writes the result URL into state file under the right field.
#
# v10.14.2 / v10.15.2 fixes:
#   - .departments iteration handles BOTH array (schema-declared) and keyed
#     object (production drift, observed on Maria's 22-dept state file).
#   - Canonical model is gpt-image-2 (KIE.AI slug). Fallback unchanged.

set -u

KIND="${1:-}"
if [[ "$KIND" != "structure" && "$KIND" != "workflow" ]]; then
  echo "usage: $0 structure|workflow" >&2
  exit 2
fi

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[infographics] no OpenClaw root" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
WS_ANSWERS_DEFAULT="$OC_ROOT/workspace/workforce-interview-answers.md"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$KIND" == "structure" ]]; then
  TEMPLATE="$SKILL_DIR/templates/infographic-1-prompt.md"
  STATE_FIELD="infographic1Url"
  STEP_LABEL="infographic-1"
else
  TEMPLATE="$SKILL_DIR/templates/infographic-2-prompt.md"
  STATE_FIELD="infographic2Url"
  STEP_LABEL="infographic-2"
fi

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2"
}

state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }

# ---- gather placeholder values ----
COMPANY_NAME=$(state_get '.companyName')
[[ -z "$COMPANY_NAME" ]] && COMPANY_NAME=$(grep -E -i '^(company name|business name)[: ]' "$WS_ANSWERS_DEFAULT" 2>/dev/null | head -1 | sed -E 's/^[^:]+:\s*//')
[[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="Your Company"

OWNER_NAME=$(state_get '.ownerName')
[[ -z "$OWNER_NAME" ]] && OWNER_NAME="the Owner"

AGENT_NAME=$(state_get '.agentName')
[[ -z "$AGENT_NAME" ]] && AGENT_NAME="the CEO Agent"

# ---- shape-tolerant department enumeration ----
#
# Schema declares .departments as an array, but production state files (e.g.
# Maria's 22-dept box) have it as a keyed object: {marketing: {...}, sales: {...}}.
# Read both shapes into a uniform [{id, name, rolesDone}] list, then derive
# DEPT_LIST + ROLE_COUNT from that.
DEPT_TYPE=$(jq -r '.departments | type' "$STATE_FILE" 2>/dev/null)
case "$DEPT_TYPE" in
  array)
    DEPT_JSON=$(jq -c '[.departments[] | {id: (.slug // .name // "dept"), name: (.name // .slug // "dept"), rolesDone: (.rolesDone // 0)}]' "$STATE_FILE" 2>/dev/null)
    ;;
  object)
    # Keyed object: use the KEY as id; .value.name if present else humanize the key.
    DEPT_JSON=$(jq -c '[.departments | to_entries[] | {id: .key, name: (.value.name // (.key | gsub("[-_]"; " "))), rolesDone: (.value.rolesDone // 0)}]' "$STATE_FILE" 2>/dev/null)
    ;;
  *)
    DEPT_JSON="[]"
    ;;
esac

DEPT_LIST=$(echo "$DEPT_JSON" | jq -r '[.[].name] | join(", ")' 2>/dev/null)
[[ -z "$DEPT_LIST" ]] && DEPT_LIST="(departments)"

ROLE_COUNT=$(echo "$DEPT_JSON" | jq -r '[.[].rolesDone] | add // 0' 2>/dev/null)
[[ -z "$ROLE_COUNT" || "$ROLE_COUNT" == "null" ]] && ROLE_COUNT="0"

BRAND_COLOR=$(state_get '.brandColor')
[[ -z "$BRAND_COLOR" ]] && BRAND_COLOR="#1a1a1a (with #D4AF37 BlackCEO gold accent)"

INDUSTRY=$(state_get '.industry')
[[ -z "$INDUSTRY" ]] && INDUSTRY="the client's industry"

# Example task, used for workflow infographic only
EXAMPLE_TASK=$(state_get '.exampleTask')
if [[ -z "$EXAMPLE_TASK" ]]; then
  case "$INDUSTRY" in
    *healthcare*|*health*|*patient*|*medical*) EXAMPLE_TASK="Onboard a new patient" ;;
    *real\ estate*|*realtor*|*property*) EXAMPLE_TASK="Launch a new listing campaign" ;;
    *coaching*|*consulting*) EXAMPLE_TASK="Onboard a new client and build their roadmap" ;;
    *marketing*|*agency*) EXAMPLE_TASK="Launch a new email campaign" ;;
    *) EXAMPLE_TASK="Complete a customer onboarding from start to finish" ;;
  esac
fi

if [[ ! -f "$TEMPLATE" ]]; then
  log "ERROR" "prompt template not found: $TEMPLATE"
  exit 1
fi

PROMPT_RAW=$(cat "$TEMPLATE")
PROMPT=$(printf '%s' "$PROMPT_RAW" \
  | sed "s|{{COMPANY_NAME}}|${COMPANY_NAME}|g" \
  | sed "s|{{OWNER_NAME}}|${OWNER_NAME}|g" \
  | sed "s|{{AGENT_NAME}}|${AGENT_NAME}|g" \
  | sed "s|{{DEPT_LIST}}|${DEPT_LIST}|g" \
  | sed "s|{{ROLE_COUNT}}|${ROLE_COUNT}|g" \
  | sed "s|{{BRAND_COLOR}}|${BRAND_COLOR}|g" \
  | sed "s|{{INDUSTRY}}|${INDUSTRY}|g" \
  | sed "s|{{EXAMPLE_TASK}}|${EXAMPLE_TASK}|g")

# ---- model selection ----
PRIMARY_MODEL="${ZHC_IMAGE_MODEL:-gpt-image-2}"
FALLBACK_MODEL="nano-banana-pro"

submit_job() {
  local model="$1"
  local prompt_json
  prompt_json=$(jq -Rs . <<< "$PROMPT")
  local body
  body=$(jq -n \
    --arg model "$model" \
    --argjson prompt "$prompt_json" \
    '{model: $model, input: {prompt: $prompt, aspect_ratio: "16:9", resolution: "2K", output_format: "png"}}')
  curl -sS --fail-with-body -X POST "https://api.kie.ai/api/v1/jobs/createTask" \
    -H "Authorization: Bearer $KIE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$body"
}

poll_job() {
  local task_id="$1"
  local elapsed=0
  local wait_sec
  while (( elapsed < 600 )); do
    local resp
    resp=$(curl -sS "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=$task_id" \
      -H "Authorization: Bearer $KIE_API_KEY" 2>/dev/null)
    local state
    state=$(echo "$resp" | jq -r '.data.state // empty' 2>/dev/null)
    case "$state" in
      success)
        echo "$resp" | jq -r '.data.resultJson' | jq -r '.resultUrls[0] // .resultUrl // .imageUrl // .url // empty' 2>/dev/null
        return 0
        ;;
      fail)
        local msg
        msg=$(echo "$resp" | jq -r '.data.failMsg // .msg // "unknown failure"')
        log "ERROR" "KIE job $task_id failed: $msg"
        return 1
        ;;
    esac
    if (( elapsed < 30 )); then wait_sec=3
    elif (( elapsed < 120 )); then wait_sec=8
    else wait_sec=20
    fi
    sleep "$wait_sec"
    elapsed=$((elapsed + wait_sec))
  done
  log "ERROR" "KIE job $task_id timed out after ${elapsed}s"
  return 1
}

# ---- retry loop ----
attempt=0
result_url=""
while (( attempt < 3 )); do
  attempt=$((attempt + 1))
  # Use primary model for attempts 1-2; fall back to fallback model on attempt 3
  if (( attempt < 3 )); then
    model="$PRIMARY_MODEL"
  else
    model="$FALLBACK_MODEL"
    log "INFO" "attempt $attempt/3: falling back to $model"
  fi
  log "INFO" "attempt $attempt/3: submitting job with model=$model"
  submit_resp=$(submit_job "$model" || true)
  task_id=$(echo "$submit_resp" | jq -r '.data.taskId // empty' 2>/dev/null)
  if [[ -z "$task_id" ]]; then
    log "WARN" "attempt $attempt: submit failed, response: $(echo "$submit_resp" | head -c 200)"
    sleep $((2 ** attempt))
    continue
  fi
  log "INFO" "attempt $attempt: submitted taskId=$task_id; polling..."
  if result_url=$(poll_job "$task_id"); then
    if [[ -n "$result_url" && "$result_url" != "null" ]]; then
      log "INFO" "attempt $attempt: success url=$result_url"
      break
    fi
  fi
  log "WARN" "attempt $attempt: did not produce a usable URL"
  result_url=""
  sleep $((2 ** attempt))
done

if [[ -z "$result_url" ]]; then
  log "ERROR" "all 3 attempts exhausted; no infographic produced"
  exit 1
fi

# ---- persist to state ----
state_set ".${STATE_FIELD} = \"$result_url\""
log "INFO" "wrote ${STATE_FIELD}=$result_url to state file"
exit 0
