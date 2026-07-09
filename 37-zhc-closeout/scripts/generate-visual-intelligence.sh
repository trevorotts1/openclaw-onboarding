#!/usr/bin/env bash
# generate-visual-intelligence.sh -- Produce the full visual intelligence image set
# for the ZHC closeout. PRD-FINAL-PACKAGE step 3: min 3, up to 30 images, each
# from its own written GPT-Image-2 prompt via Kie.ai createTask.
#
# The mandatory set (always generated):
#   1. Org flow chart          -- templates/infographic-1-prompt.md  (GPT-Image-2)
#   2. What Is a ZHC           -- templates/img-what-is-zhc-prompt.md
#   3. How Your ZHC Works      -- templates/img-how-your-zhc-works-prompt.md
#
# Additional images (generated up to ZHC_VISUAL_INTEL_CAP, default 10, max 30):
#   4. Dept overview           -- templates/img-dept-overview-prompt.md
#   5. SOP system              -- templates/img-sop-system-prompt.md
#   6. Lean Six Sigma          -- templates/img-six-sigma-prompt.md
#
# Model: gpt-image-2-text-to-image (PRIMARY per PRD fork decision).
# Fallback: nano-banana-2.
# Override primary via ZHC_IMAGE_MODEL env var.
#
# All generated URLs are written to state:
#   .visualIntelligenceUrls  (array, all image URLs in order)
#   .infographic1Url         (org chart -- for backward compat)
#   .infographic2Url         (how-your-zhc-works -- for backward compat)
#
# Idempotent: if .visualIntelligenceUrls already has >=3 entries, exits 0.
#
# 8.5 QUALITY GATE: after generation, agent must self-rate each image 1-10
# vs the rubric in QUALITY-GATE.md and write .qualityRatings into state.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[visual-intel] no OpenClaw root" >&2
  exit 1
fi

STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT}/workspace/.workforce-build-state.json}"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STEP_LABEL="visual-intelligence"

# Max images (min 3 required, cap at 30)
CAP="${ZHC_VISUAL_INTEL_CAP:-10}"
[[ "$CAP" -gt 30 ]] && CAP=30
[[ "$CAP" -lt 3 ]] && CAP=3

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2"
}
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
# SK1-13: shared, concurrency-safe state_set (portable mkdir-mutex + stale-lock
# breaker) replaces the former unlocked jq->tmp->mv copy, so a resume-cron write
# can never lost-update a concurrent run-closeout write. See lib-closeout-state.sh.
# shellcheck source=lib-closeout-state.sh disable=SC1090,SC1091
if ! source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-closeout-state.sh" 2>/dev/null; then
  # Fallback for an older bundle without the shared lib: unlocked atomic write.
  state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }
fi

# ---- idempotency check ----
existing_count=$(state_get '.visualIntelligenceUrls | length' 2>/dev/null || echo "0")
[[ -z "$existing_count" || "$existing_count" == "null" ]] && existing_count=0
if [[ "$existing_count" -ge 3 ]]; then
  log "INFO" "visualIntelligenceUrls already has $existing_count entries -- skipping (idempotent)"
  exit 0
fi

# ---- gather placeholders ----
COMPANY_NAME=$(state_get '.companyName'); [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="Your Company"
OWNER_NAME=$(state_get '.ownerName'); [[ -z "$OWNER_NAME" ]] && OWNER_NAME="the Owner"
AGENT_NAME=$(state_get '.agentName'); [[ -z "$AGENT_NAME" ]] && AGENT_NAME="the CEO Agent"
INDUSTRY=$(state_get '.industry'); [[ -z "$INDUSTRY" ]] && INDUSTRY="modern business"
BRAND_COLOR=$(state_get '.brandColor'); [[ -z "$BRAND_COLOR" ]] && BRAND_COLOR="#1a1a1a (with #D4AF37 gold accent)"

# Department enumeration
DEPT_TYPE=$(jq -r '.departments | type' "$STATE_FILE" 2>/dev/null || echo "null")
case "$DEPT_TYPE" in
  array)
    DEPT_JSON=$(jq -c '[.departments[] | {slug: (.slug // .name // "dept"), name: (.name // .slug // "dept"), roles: (.rolesDone // .roles // 0)}]' "$STATE_FILE" 2>/dev/null || echo "[]")
    ;;
  object)
    DEPT_JSON=$(jq -c '[.departments | to_entries[] | {slug: .key, name: (.value.name // (.key | gsub("[-_]"; " "))), roles: (.value.rolesDone // .value.roles // 0)}]' "$STATE_FILE" 2>/dev/null || echo "[]")
    ;;
  *)
    DEPT_JSON="[]"
    ;;
esac
DEPT_LIST=$(echo "$DEPT_JSON" | jq -r '[.[].name] | join(", ")' 2>/dev/null || echo "(departments)")
DEPT_COUNT=$(echo "$DEPT_JSON" | jq 'length' 2>/dev/null || echo "0")
ROLE_COUNT=$(echo "$DEPT_JSON" | jq '[.[].roles] | add // 0' 2>/dev/null || echo "0")

# What the business delivers (for prompt placeholders)
WHAT_THEY_DELIVER=$(state_get '.whatYouDeliver // .whatTheyDeliver // .coreDeliverable')
if [[ -z "$WHAT_THEY_DELIVER" ]]; then
  case "$INDUSTRY" in
    *grant*|*funding*|*nonprofit*) WHAT_THEY_DELIVER="approved, funded grant" ;;
    *healthcare*|*health*|*medical*) WHAT_THEY_DELIVER="completed patient deliverable" ;;
    *real\ estate*|*realtor*|*property*) WHAT_THEY_DELIVER="closed listing package" ;;
    *coaching*|*consulting*) WHAT_THEY_DELIVER="finished client roadmap" ;;
    *marketing*|*agency*) WHAT_THEY_DELIVER="published campaign" ;;
    *) WHAT_THEY_DELIVER="finished, approved deliverable" ;;
  esac
fi

# ---- substitute template placeholders ----
fill_prompt() {
  local text="$1"
  text="${text//\{\{COMPANY_NAME\}\}/$COMPANY_NAME}"
  text="${text//\{\{OWNER_NAME\}\}/$OWNER_NAME}"
  text="${text//\{\{AGENT_NAME\}\}/$AGENT_NAME}"
  text="${text//\{\{INDUSTRY\}\}/$INDUSTRY}"
  text="${text//\{\{BRAND_COLOR\}\}/$BRAND_COLOR}"
  text="${text//\{\{DEPT_LIST\}\}/$DEPT_LIST}"
  text="${text//\{\{DEPT_COUNT\}\}/$DEPT_COUNT}"
  text="${text//\{\{ROLE_COUNT\}\}/$ROLE_COUNT}"
  text="${text//\{\{WHAT_THEY_DELIVER\}\}/$WHAT_THEY_DELIVER}"
  echo "$text"
}

# ---- KIE API helpers ----
PRIMARY_MODEL="${ZHC_IMAGE_MODEL:-gpt-image-2-text-to-image}"
FALLBACK_MODEL="nano-banana-2"

submit_job() {
  local model="$1"
  local prompt_text="$2"
  local prompt_json
  prompt_json=$(jq -Rs . <<< "$prompt_text")
  local body
  body=$(jq -n \
    --arg model "$model" \
    --argjson prompt "$prompt_json" \
    '{model: $model, input: {prompt: $prompt, aspect_ratio: "16:9", resolution: "2K", output_format: "png"}}')
  curl -sS --fail-with-body -X POST "https://api.kie.ai/api/v1/jobs/createTask" \
    -H "Authorization: Bearer ${KIE_API_KEY:-}" \
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
      -H "Authorization: Bearer ${KIE_API_KEY:-}" 2>/dev/null)
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

# generate_image <prompt_file> <label>
# Returns the URL on stdout; exits non-zero on failure.
generate_image() {
  local prompt_file="$1"
  local label="$2"
  if [[ ! -f "$prompt_file" ]]; then
    log "ERROR" "prompt template not found: $prompt_file (label=$label)"
    return 1
  fi
  local raw_prompt
  raw_prompt=$(cat "$prompt_file")
  local prompt
  prompt=$(fill_prompt "$raw_prompt")

  local attempt=0
  local cur_model="$PRIMARY_MODEL"
  local result_url=""
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    if (( attempt == 3 )) && [[ "$cur_model" == "$PRIMARY_MODEL" ]]; then
      cur_model="$FALLBACK_MODEL"
      log "INFO" "[$label] attempt $attempt/3: falling back to $cur_model"
    fi
    log "INFO" "[$label] attempt $attempt/3: submitting with model=$cur_model"
    local submit_resp
    submit_resp=$(submit_job "$cur_model" "$prompt" || true)
    local task_id
    task_id=$(echo "$submit_resp" | jq -r '.data.taskId // empty' 2>/dev/null)
    if [[ -z "$task_id" ]]; then
      local submit_err
      submit_err=$(echo "$submit_resp" | head -c 300)
      log "WARN" "[$label] attempt $attempt: submit failed: $submit_err"
      # If primary rejected as not-supported, switch to fallback immediately
      if [[ "$cur_model" == "$PRIMARY_MODEL" && "$cur_model" != "$FALLBACK_MODEL" ]] \
         && echo "$submit_err" | grep -qiE 'model name not supported|not supported|422'; then
        log "WARN" "[$label] primary model not supported on this account; switching to fallback"
        cur_model="$FALLBACK_MODEL"
      fi
      sleep $((2 ** attempt))
      continue
    fi
    log "INFO" "[$label] submitted taskId=$task_id; polling..."
    if result_url=$(poll_job "$task_id"); then
      if [[ -n "$result_url" && "$result_url" != "null" ]]; then
        log "INFO" "[$label] success url=$result_url"
        echo "$result_url"
        return 0
      fi
    fi
    log "WARN" "[$label] attempt $attempt: no usable URL"
    result_url=""
    sleep $((2 ** attempt))
  done
  log "ERROR" "[$label] all 3 attempts exhausted -- no image produced"
  return 1
}

# ---- build the ordered prompt list ----
# Each entry: <label>|<prompt_file>
# Mandatory 3 come first. Additional up to cap.
declare -a PROMPT_QUEUE=(
  "org-flowchart|$SKILL_DIR/templates/infographic-1-prompt.md"
  "what-is-zhc|$SKILL_DIR/templates/img-what-is-zhc-prompt.md"
  "how-your-zhc-works|$SKILL_DIR/templates/img-how-your-zhc-works-prompt.md"
  "dept-overview|$SKILL_DIR/templates/img-dept-overview-prompt.md"
  "sop-system|$SKILL_DIR/templates/img-sop-system-prompt.md"
  "six-sigma|$SKILL_DIR/templates/img-six-sigma-prompt.md"
  "workflow-infographic|$SKILL_DIR/templates/infographic-2-prompt.md"
)

# ---- run generation loop ----
RESULT_URLS=()
generated=0
for entry in "${PROMPT_QUEUE[@]}"; do
  [[ "$generated" -ge "$CAP" ]] && break
  label="${entry%%|*}"
  pfile="${entry##*|}"
  log "INFO" "generating image [$((generated+1))/$CAP]: $label"
  url=$(generate_image "$pfile" "$label" || true)
  if [[ -n "$url" && "$url" != "null" ]]; then
    RESULT_URLS+=("$url")
    generated=$((generated + 1))
    log "INFO" "[$label] added to visual intelligence set ($generated/$CAP)"
  else
    log "WARN" "[$label] failed to generate -- continuing with remaining images"
  fi
done

if [[ "${#RESULT_URLS[@]}" -lt 3 ]]; then
  log "ERROR" "visual intelligence set produced only ${#RESULT_URLS[@]} images (minimum 3 required)"
  exit 1
fi

# ---- write results to state ----
# Build JSON array of URLs
URL_ARRAY=$(printf '%s\n' "${RESULT_URLS[@]}" | jq -R . | jq -s .)
state_set ".visualIntelligenceUrls = $URL_ARRAY"

# Backward compat: write infographic1Url (org chart) and infographic2Url (how-your-zhc-works)
# Org chart is always index 0; how-zhc-works is always index 1 in the mandatory set.
if [[ "${#RESULT_URLS[@]}" -ge 1 ]]; then
  state_set ".infographic1Url = \"${RESULT_URLS[0]}\""
fi
if [[ "${#RESULT_URLS[@]}" -ge 3 ]]; then
  # Index 2 is how-your-zhc-works
  state_set ".infographic2Url = \"${RESULT_URLS[2]}\""
elif [[ "${#RESULT_URLS[@]}" -ge 2 ]]; then
  state_set ".infographic2Url = \"${RESULT_URLS[1]}\""
fi

log "INFO" "visual intelligence set complete: ${#RESULT_URLS[@]} images written to state (.visualIntelligenceUrls)"
log "INFO" "8.5-GATE: each image must be self-rated 1-10 vs the rubric in QUALITY-GATE.md. Write .qualityRatings per image. Do NOT deliver below 8.5 -- regenerate and re-rate."
exit 0
