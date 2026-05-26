#!/usr/bin/env bash
# generate-celebration-video.sh - ZHC celebration video, with local MP4 download.
#
# Model strategy (v10.14.3 / v10.15.3, codified from Maria Anderson / Marico
# Consulting 2026-05-26 closeout lessons):
#
#   DEFAULT for Skill 37 celebration: Gemini Omni Video via KIE.ai
#     (model slug: gemini-omni-video). Reason: Gemini Omni accepts image
#     references (we can hand it the just-rendered workforce-chart PNG so
#     brand colors and CEO agent name carry through into the video).
#     Endpoint: POST /api/v1/jobs/createTask + GET /api/v1/jobs/recordInfo
#
#   FALLBACK: Veo 3.1 via KIE.ai (model slug: veo3 or veo3_fast).
#     Veo 3.1 / veo3_fast is the GENERAL-PURPOSE default video model
#     elsewhere in OpenClaw - it just isn't ideal for *this* celebration
#     use case because Veo3 cannot accept an image guidance reference.
#     Endpoint: POST /api/v1/veo/generate + GET /api/v1/veo/record-info
#
# Env overrides:
#   ZHC_CELEBRATION_VIDEO_MODEL  default: gemini-omni-video
#                                accepts:  gemini-omni-video | veo3 | veo3_fast
#   ZHC_VIDEO_DURATION           default: 4 (Gemini) or 8 (Veo)
#                                Gemini Omni typically supports 4-8s.
#                                Veo3 supports 4, 6, or 8s.
#
# CRITICAL (Lesson 2): NEVER pass tempfile.aiquickdraw.com URLs directly to
# Telegram. The CDN returns content-disposition: attachment, so Telegram
# renders the message as a download card rather than an inline video player.
# This script ALWAYS downloads the MP4 bytes to disk first, then exports
# the LOCAL path so the Telegram step can upload via Telegram's multipart
# sendVideo endpoint.

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
LOCAL_MP4="$OC_ROOT/workspace/.zhc-celebration-video.mp4"

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
INFOGRAPHIC1_URL=$(state_get '.infographic1Url')

if [[ ! -f "$TEMPLATE" ]]; then
  log "ERROR" "video prompt template missing: $TEMPLATE"
  exit 1
fi

PROMPT=$(cat "$TEMPLATE" \
  | sed "s|{{COMPANY_NAME}}|${COMPANY_NAME}|g" \
  | sed "s|{{OWNER_NAME}}|${OWNER_NAME}|g" \
  | sed "s|{{AGENT_NAME}}|${AGENT_NAME}|g" \
  | sed "s|{{INDUSTRY}}|${INDUSTRY}|g")

MODEL="${ZHC_CELEBRATION_VIDEO_MODEL:-${ZHC_VIDEO_MODEL:-gemini-omni-video}}"

# Snap duration to a model-valid value.
DURATION_INPUT="${ZHC_VIDEO_DURATION:-}"
case "$MODEL" in
  gemini-omni-video)
    # Gemini Omni Video accepts 4-8 (passed as a string per docs).
    case "$DURATION_INPUT" in
      4|5|6|7|8) DURATION="$DURATION_INPUT" ;;
      "")        DURATION="4" ;;
      *)
        log "WARN" "ZHC_VIDEO_DURATION='$DURATION_INPUT' is out of Gemini Omni range (4-8); falling back to 4"
        DURATION="4"
        ;;
    esac
    ;;
  veo3|veo3_fast)
    case "$DURATION_INPUT" in
      4|6|8) DURATION="$DURATION_INPUT" ;;
      "")    DURATION="8" ;;
      *)
        log "WARN" "ZHC_VIDEO_DURATION='$DURATION_INPUT' is not a Veo duration (4/6/8); falling back to 8"
        DURATION="8"
        ;;
    esac
    ;;
  *)
    log "WARN" "unrecognized ZHC_CELEBRATION_VIDEO_MODEL=$MODEL; falling back to gemini-omni-video"
    MODEL="gemini-omni-video"
    DURATION="4"
    ;;
esac

# ----------------------------------------------------------------------
# Submit + poll: Gemini Omni Video
# ----------------------------------------------------------------------
submit_gemini_omni() {
  local input_obj
  if [[ -n "$INFOGRAPHIC1_URL" && "$INFOGRAPHIC1_URL" != "null" && "$INFOGRAPHIC1_URL" != file://* ]]; then
    input_obj=$(jq -n \
      --arg prompt "$PROMPT" \
      --arg img "$INFOGRAPHIC1_URL" \
      --arg dur "$DURATION" \
      '{prompt: $prompt, image_urls: [$img], duration: $dur}')
  else
    input_obj=$(jq -n \
      --arg prompt "$PROMPT" \
      --arg dur "$DURATION" \
      '{prompt: $prompt, duration: $dur}')
  fi
  local body
  body=$(jq -n \
    --arg model "$MODEL" \
    --argjson input "$input_obj" \
    '{model: $model, input: $input}')
  curl -sS --fail-with-body -X POST "https://api.kie.ai/api/v1/jobs/createTask" \
    -H "Authorization: Bearer $KIE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$body"
}

poll_gemini_omni() {
  local task_id="$1"
  local elapsed=0
  local wait_sec
  while (( elapsed < 900 )); do
    local resp
    resp=$(curl -sS "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=$task_id" \
      -H "Authorization: Bearer $KIE_API_KEY" 2>/dev/null)
    local state
    state=$(echo "$resp" | jq -r '.data.state // empty' 2>/dev/null)
    case "$state" in
      success)
        echo "$resp" | jq -r '.data.resultJson' 2>/dev/null \
          | jq -r '.resultUrls[0] // .videoUrl // .url // .resultUrl // empty' 2>/dev/null
        return 0
        ;;
      fail)
        local msg
        msg=$(echo "$resp" | jq -r '.data.failMsg // .msg // "unknown failure"')
        log "ERROR" "Gemini Omni job $task_id failed: $msg"
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
  log "ERROR" "Gemini Omni job $task_id timed out after ${elapsed}s"
  return 1
}

# ----------------------------------------------------------------------
# Submit + poll: Veo 3.x (general-purpose fallback)
# ----------------------------------------------------------------------
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
  while (( elapsed < 900 )); do
    local resp http_code
    resp=$(curl -sS -w '\n__HTTP_CODE__%{http_code}' \
      "https://api.kie.ai/api/v1/veo/record-info?taskId=$task_id" \
      -H "Authorization: Bearer $KIE_API_KEY" 2>/dev/null)
    http_code=$(printf '%s' "$resp" | awk -F'__HTTP_CODE__' 'END{print $2}')
    resp=$(printf '%s' "$resp" | sed 's/__HTTP_CODE__[0-9]*$//')

    if [[ -n "$http_code" && "$http_code" =~ ^[45] ]]; then
      log "ERROR" "VEO poll HTTP $http_code for $task_id: $(echo "$resp" | head -c 200)"
      if [[ "$http_code" =~ ^4 ]]; then return 1; fi
    fi

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

# ----------------------------------------------------------------------
# Retry loop with model fallback. Attempts 1+2 use the configured primary;
# if both fail, attempt 3 falls back to veo3_fast (unless already Veo).
# ----------------------------------------------------------------------
PRIMARY_MODEL="$MODEL"
attempt=0
result_url=""
while (( attempt < 3 )); do
  attempt=$((attempt + 1))
  if (( attempt == 3 )) && [[ "$MODEL" == "gemini-omni-video" ]]; then
    MODEL="veo3_fast"
    DURATION="8"
    log "INFO" "attempt $attempt: falling back to $MODEL (general-purpose video default)"
  fi

  log "INFO" "attempt $attempt/3: submitting video job model=$MODEL duration=${DURATION}s"
  case "$MODEL" in
    gemini-omni-video)
      submit_resp=$(submit_gemini_omni || true)
      task_id=$(echo "$submit_resp" | jq -r '.data.taskId // .taskId // empty' 2>/dev/null)
      if [[ -n "$task_id" ]]; then
        log "INFO" "attempt $attempt: submitted gemini-omni-video taskId=$task_id"
        result_url=$(poll_gemini_omni "$task_id" || true)
      fi
      ;;
    veo3|veo3_fast)
      submit_resp=$(submit_veo || true)
      task_id=$(echo "$submit_resp" | jq -r '.data.taskId // .taskId // empty' 2>/dev/null)
      if [[ -n "$task_id" ]]; then
        log "INFO" "attempt $attempt: submitted veo taskId=$task_id"
        result_url=$(poll_veo "$task_id" || true)
      fi
      ;;
  esac

  if [[ -z "${task_id:-}" ]]; then
    log "WARN" "attempt $attempt: submit failed, response: $(echo "${submit_resp:-}" | head -c 200)"
    sleep $((4 ** attempt))
    continue
  fi
  if [[ -n "$result_url" && "$result_url" != "null" ]]; then
    log "INFO" "attempt $attempt: success remote-url=$result_url"
    break
  fi
  log "WARN" "attempt $attempt: did not produce a usable URL"
  result_url=""
  sleep $((4 ** attempt))
done

if [[ -z "$result_url" ]]; then
  log "ERROR" "all attempts exhausted; no celebration video produced"
  exit 1
fi

# ----------------------------------------------------------------------
# CRITICAL: download MP4 bytes locally so the Telegram step can upload.
# (Telegram cannot inline-render a tempfile.aiquickdraw.com URL because the
# CDN serves it with content-disposition: attachment.)
# ----------------------------------------------------------------------
log "INFO" "downloading celebration video bytes to $LOCAL_MP4"
if ! curl -fL --max-time 180 -o "$LOCAL_MP4" "$result_url" >> "$LOG_FILE" 2>&1; then
  log "ERROR" "failed to download celebration video bytes from $result_url"
  exit 1
fi
if [[ ! -s "$LOCAL_MP4" ]]; then
  log "ERROR" "downloaded video file is empty at $LOCAL_MP4"
  exit 1
fi

# Soft-verify it's actually MP4 / ISO Media. We don't fail hard on this
# because `file` may not be installed on every container - but we log it.
if command -v file >/dev/null 2>&1; then
  FTYPE=$(file -b "$LOCAL_MP4" 2>/dev/null || true)
  log "INFO" "downloaded file type: $FTYPE"
  case "$FTYPE" in
    *"ISO Media"*|*"MP4"*|*"mp4"*) ;;
    *) log "WARN" "downloaded file does not look like MP4: $FTYPE" ;;
  esac
fi

state_set ".celebrationVideoUrl = \"$result_url\" | .celebrationVideoLocalPath = \"$LOCAL_MP4\" | .celebrationVideoModel = \"$PRIMARY_MODEL\""
log "INFO" "wrote celebrationVideoUrl=$result_url + celebrationVideoLocalPath=$LOCAL_MP4 to state"
exit 0
