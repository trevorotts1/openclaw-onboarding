#!/usr/bin/env bash
# generate-celebration-video.sh - ZHC celebration video, with local MP4 download.
#
# Model strategy (v10.14.3 / v10.15.3, codified from live fleet closeout
# lessons, 2026-05-26):
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
#   ZHC_CELEBRATION_VIDEO_ASPECT default: 16:9. Accepts 16:9 or 9:16.
#                                (KIE Gemini Omni only supports those two.)
#   ZHC_VIDEO_POLL_TIMEOUT_SEC   default: 1800 (was 900 in v10.X.3).
#                                Veo3 jobs commonly take 5-20 min; 900s
#                                aborted before completion on a prior run.
#
# v10.X.4 fixes (2026-05-26 closeout postmortem):
#   - submit_gemini_omni() now always sets aspect_ratio (KIE 422 fix)
#   - VEO poll timeout bumped to 1800s + transient 500 retry (max 3)
#
# PUBLIC-REFERENCE-IMAGE fix (2026-06-20 closeout postmortem -- recurring
# "Gemini Omni: Image fetch failed" across multiple recent closeouts):
#   ROOT CAUSE: the reference images handed to the video model were not
#   reliably reachable by KIE/Gemini's own servers. The org-chart infographic
#   (infographic1Url) is rendered LOCALLY and stored as a file:// path; the
#   AI-generated infographics are stored as KIE tempfile.* URLs that auto-delete
#   after a few days and whose CDN the Gemini Omni backend intermittently
#   cannot fetch. file:// was silently dropped (losing the brand reference) and
#   tempfile URLs were passed verbatim with NO retry -> "Image fetch failed".
#   FIX: ensure_public_url() now GUARANTEES every reference image is a fresh,
#   durable, model-reachable https URL BEFORE the video call:
#     - file:// or on-disk path -> KIE base64 upload (file-base64-upload)
#     - existing http(s) URL     -> KIE re-host (file-url-upload), so an expired
#                                   or flaky tempfile becomes a fresh KIE-hosted
#                                   URL the model can fetch.
#   Both uploaders retry-with-backoff. submit_gemini_omni()/poll also treat
#   "image fetch failed" as a transient and retry. Endpoints (KIE, same key):
#     POST https://kieai.redpandaai.co/api/file-base64-upload
#     POST https://kieai.redpandaai.co/api/file-url-upload
#   (see 07-kie-setup/kie-setup-full.md "File upload APIs"). Uploaded files are
#   retained ~3 days -- ample for the closeout window. If a reference still can't
#   be made public, it is simply OMITTED (the video renders prompt-only) rather
#   than poisoning the request with an unfetchable URL.
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

STATE_FILE="${ZHC_STATE_FILE:-$OC_ROOT/workspace/.workforce-build-state.json}"
LOG_FILE="${ZHC_LOG_FILE:-$OC_ROOT/workspace/.zhc-closeout.log}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$SKILL_DIR/templates/veo-prompt.txt"
STEP_LABEL="celebration-video"
LOCAL_MP4="$OC_ROOT/workspace/.zhc-celebration-video.mp4"

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  # Console copy goes to STDERR, never STDOUT. Several helpers below have their
  # STDOUT captured by command substitution (submit_*, poll_*, ensure_public_url,
  # _upload_*). Logging to stdout would poison those captures (e.g. a warning line
  # interleaved into the createTask JSON response broke task_id extraction).
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >&2
}
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }

# ----------------------------------------------------------------------
# PUBLIC REFERENCE IMAGE RESOLUTION (2026-06-20 "Image fetch failed" fix)
#
# The video model (Gemini Omni via KIE) downloads each reference image from
# its OWN servers. So every reference MUST be a publicly reachable https URL.
# Two failure modes we have to defeat:
#   1. file:// / on-disk path  -> not reachable by anyone but this box.
#   2. ephemeral / flaky URL   -> e.g. a KIE tempfile.* that has expired or a
#      CDN the model backend intermittently cannot pull -> "Image fetch failed".
#
# KIE_UPLOAD_BASE: the KIE temp-file upload service (07-kie-setup). It returns a
# durable (~3 day) KIE-hosted https URL that the SAME KIE/Gemini backend can
# always fetch. Overridable for tests.
KIE_UPLOAD_BASE="${KIE_UPLOAD_BASE:-https://kieai.redpandaai.co}"
# KIE_API_BASE: the createTask/recordInfo + veo job API host. Overridable for
# tests (lets the harness point the whole pipeline at a local mock). Production
# default is the real KIE host.
KIE_API_BASE="${KIE_API_BASE:-https://api.kie.ai}"
# Re-host EVERY reference (even already-public ones) so the model always gets a
# fresh, first-party KIE URL? Default on -- this is what kills the recurring
# transient "Image fetch failed" on tempfile/CDN URLs. Set 0 to pass through
# already-public http(s) URLs unchanged.
ZHC_REHOST_PUBLIC_REFS="${ZHC_REHOST_PUBLIC_REFS:-1}"

# _is_local_path <str> -> 0 if it is a file:// URL or an on-disk path.
_is_local_path() {
  local u="$1"
  [[ "$u" == file://* ]] && return 0
  [[ "$u" == /* && -e "$u" ]] && return 0   # absolute path that exists on disk
  return 1
}

# _local_to_disk <str> -> strips file:// to a plain filesystem path on stdout.
_local_to_disk() {
  local u="$1"
  [[ "$u" == file://* ]] && u="${u#file://}"
  printf '%s' "$u"
}

# _mime_for <path> -> best-effort image mime type for the base64 data URL.
_mime_for() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    *.png)         echo "image/png" ;;
    *.jpg|*.jpeg)  echo "image/jpeg" ;;
    *.webp)        echo "image/webp" ;;
    *.gif)         echo "image/gif" ;;
    *)             echo "image/png" ;;
  esac
}

# _curl_retry: POST a JSON body with retry-with-backoff on transient failures.
# Echoes the response body; returns non-zero only after all attempts fail.
# Treats HTTP 5xx / 429 / 408 / connection failures as transient.
#
# Args: <url> <body> <label> [attempts] [body_file]
#   body_file (5th arg, optional): when set, the request body is read FROM THIS
#   FILE via curl --data-binary @file instead of being passed inline as a
#   command-line argument. This is MANDATORY for the base64 image-upload body:
#   a >~128KB base64 payload passed through argv ("-d $body") overflows ARG_MAX
#   and the whole call dies with "Argument list too long" (the recurring brand
#   reference-image upload failure). Reading the body from a file keeps the big
#   payload off the argument list entirely. $body is ignored when $body_file set.
_curl_retry_post() {
  local url="$1"; local body="$2"; local label="$3"
  local attempts="${4:-4}"
  local body_file="${5:-}"
  local i resp http_code rc
  # Build the data argument array once: read from file (no argv limit) when a
  # body_file is provided, otherwise inline the (small) body string.
  local data_args
  if [[ -n "$body_file" ]]; then
    data_args=(--data-binary "@$body_file")
  else
    data_args=(-d "$body")
  fi
  for (( i=1; i<=attempts; i++ )); do
    resp=$(curl -sS -m 60 -w '\n__HTTP_CODE__%{http_code}' -X POST "$url" \
      -H "Authorization: Bearer ${KIE_API_KEY:-}" \
      -H "Content-Type: application/json" \
      "${data_args[@]}" 2>/dev/null)
    rc=$?
    http_code=$(printf '%s' "$resp" | awk -F'__HTTP_CODE__' 'END{print $2}')
    resp=$(printf '%s' "$resp" | sed 's/__HTTP_CODE__[0-9]*$//')
    if [[ $rc -eq 0 && "$http_code" =~ ^2 ]]; then
      printf '%s' "$resp"
      return 0
    fi
    # transient? (curl failure, or 408/429/5xx)
    if [[ $rc -ne 0 || "$http_code" =~ ^5 || "$http_code" == "429" || "$http_code" == "408" || -z "$http_code" ]]; then
      log "WARN" "$label: transient failure (rc=$rc http=${http_code:-none}, attempt $i/$attempts); retrying"
      sleep $(( i * i * 2 ))
      continue
    fi
    # any other 4xx is terminal for this call
    log "WARN" "$label: non-retryable HTTP ${http_code}: $(printf '%s' "$resp" | head -c 160)"
    return 1
  done
  log "WARN" "$label: exhausted $attempts attempts"
  return 1
}

# _upload_local_to_public <disk_path> -> echoes a public KIE URL, or non-zero.
_upload_local_to_public() {
  local path; path="$(_local_to_disk "$1")"
  if [[ ! -s "$path" ]]; then
    log "WARN" "ref-upload: local file missing/empty: $path"
    return 1
  fi
  if [[ -z "${KIE_API_KEY:-}" ]]; then
    log "WARN" "ref-upload: KIE_API_KEY unset; cannot upload local reference $path"
    return 1
  fi
  local mime fname resp url b64_file body_file
  mime="$(_mime_for "$path")"
  fname="zhc-ref-$(date -u +%s)-$(basename "$path")"

  # ARG-LIST-TOO-LONG fix (recurring brand-image failure): the reference image's
  # base64 must NEVER touch the command line. Previously the full base64 was
  # interpolated into `jq -n --arg data "data:...;base64,${b64}"` (and then into
  # `curl -d "$body"`). For any image >~128KB this overflows ARG_MAX and the
  # whole upload dies with "jq: Argument list too long", so the brand reference
  # silently never reached the video model. FIX: stream the base64 to a temp
  # file, read it INTO jq via --rawfile (no argv), build the JSON body to a
  # second temp file, and POST it with curl --data-binary @file (no argv).
  b64_file="$(mktemp "${TMPDIR:-/tmp}/zhc-ref-b64.XXXXXX")"
  body_file="$(mktemp "${TMPDIR:-/tmp}/zhc-ref-body.XXXXXX")"
  # base64 with no line wrapping. GNU coreutils uses -w0; BSD/macOS base64 has no
  # -w flag and never wraps by default. Try -w0, fall back to plain + strip \n.
  if ! base64 -w0 < "$path" > "$b64_file" 2>/dev/null; then
    base64 < "$path" 2>/dev/null | tr -d '\n' > "$b64_file"
  fi
  if [[ ! -s "$b64_file" ]]; then
    log "WARN" "ref-upload: base64 of $path produced no data"
    rm -f "$b64_file" "$body_file"
    return 1
  fi
  # --rawfile data <file> binds $data to the file's raw contents (the base64),
  # bypassing the argument list entirely. The data: prefix is concatenated
  # inside jq so the giant string is never an argv element.
  if ! jq -n \
    --rawfile data "$b64_file" \
    --arg prefix "data:${mime};base64," \
    --arg p "images/zhc-closeout" \
    --arg f "$fname" \
    '{base64Data: ($prefix + ($data | rtrimstr("\n"))), uploadPath: $p, fileName: $f}' \
    > "$body_file"; then
    log "WARN" "ref-upload: jq failed to build base64 upload body for $path"
    rm -f "$b64_file" "$body_file"
    return 1
  fi
  resp=$(_curl_retry_post "$KIE_UPLOAD_BASE/api/file-base64-upload" "" "ref-upload(base64)" 4 "$body_file") || {
    rm -f "$b64_file" "$body_file"; return 1
  }
  rm -f "$b64_file" "$body_file"
  url=$(printf '%s' "$resp" | jq -r '.data.downloadUrl // .downloadUrl // .data.url // empty' 2>/dev/null)
  if [[ -n "$url" && "$url" == http* ]]; then
    printf '%s' "$url"
    return 0
  fi
  log "WARN" "ref-upload(base64): no downloadUrl in response: $(printf '%s' "$resp" | head -c 160)"
  return 1
}

# _rehost_url_to_public <http_url> -> echoes a fresh KIE-hosted URL, or non-zero.
_rehost_url_to_public() {
  local src="$1"
  if [[ -z "${KIE_API_KEY:-}" ]]; then
    log "WARN" "ref-rehost: KIE_API_KEY unset; cannot re-host $src"
    return 1
  fi
  local fname body resp url
  fname="zhc-ref-$(date -u +%s).png"
  body=$(jq -n \
    --arg u "$src" \
    --arg p "images/zhc-closeout" \
    --arg f "$fname" \
    '{fileUrl: $u, uploadPath: $p, fileName: $f}')
  resp=$(_curl_retry_post "$KIE_UPLOAD_BASE/api/file-url-upload" "$body" "ref-rehost(url)") || return 1
  url=$(printf '%s' "$resp" | jq -r '.data.downloadUrl // .downloadUrl // .data.url // empty' 2>/dev/null)
  if [[ -n "$url" && "$url" == http* ]]; then
    printf '%s' "$url"
    return 0
  fi
  log "WARN" "ref-rehost(url): no downloadUrl in response: $(printf '%s' "$resp" | head -c 160)"
  return 1
}

# ensure_public_url <raw_ref> -> echoes a model-reachable https URL on stdout,
# or echoes nothing + returns non-zero if the ref cannot be made public (the
# caller then OMITS it rather than poisoning the request). Idempotent + cached.
ensure_public_url() {
  local raw="$1"
  [[ -z "$raw" || "$raw" == "null" ]] && return 1
  if _is_local_path "$raw"; then
    _upload_local_to_public "$raw" && return 0
    return 1
  fi
  if [[ "$raw" == http://* || "$raw" == https://* ]]; then
    if [[ "$ZHC_REHOST_PUBLIC_REFS" == "1" ]]; then
      # Re-host to a fresh first-party KIE URL. On failure, fall back to the
      # original URL (better to try the original than to drop the reference).
      local rehosted
      if rehosted="$(_rehost_url_to_public "$raw")"; then
        printf '%s' "$rehosted"
        return 0
      fi
      log "WARN" "ref: re-host failed for $raw; falling back to original public URL"
    fi
    printf '%s' "$raw"
    return 0
  fi
  # unknown scheme -> not usable
  log "WARN" "ref: unrecognized reference '$raw' (not file://, path, or http[s]); omitting"
  return 1
}

COMPANY_NAME=$(state_get '.companyName'); [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="Your Company"
OWNER_NAME=$(state_get '.ownerName'); [[ -z "$OWNER_NAME" ]] && OWNER_NAME="the Owner"
AGENT_NAME=$(state_get '.agentName'); [[ -z "$AGENT_NAME" ]] && AGENT_NAME="the CEO Agent"
INDUSTRY=$(state_get '.industry'); [[ -z "$INDUSTRY" ]] && INDUSTRY="modern business"
INFOGRAPHIC1_URL=$(state_get '.infographic1Url')
# Read client logo URL from branding-questions.json capture (PRD step 4 -- logo fix)
LOGO_URL=$(state_get '.logoUrl // .logo_url')
[[ "$LOGO_URL" == "null" ]] && LOGO_URL=""
if [[ -z "$LOGO_URL" ]]; then
  # Fallback: search branding-questions.json in the workspace
  _branding_file=""
  for _bf in "$OC_ROOT/workspace/branding-questions.json" "$OC_ROOT/workspace/.branding-questions.json"; do
    [[ -f "$_bf" ]] && _branding_file="$_bf" && break
  done
  if [[ -n "$_branding_file" ]]; then
    LOGO_URL=$(jq -r '.logo_url // .logoUrl // .logo // empty' "$_branding_file" 2>/dev/null || true)
    [[ "$LOGO_URL" == "null" ]] && LOGO_URL=""
  fi
fi

# ----------------------------------------------------------------------
# Make every reference image PUBLIC before the video call (Image-fetch fix).
# After this block, INFOGRAPHIC1_URL / LOGO_URL are EITHER a model-reachable
# https URL OR empty (omitted). The on-disk org-chart PNG is preferred as the
# source for infographic1 when present, since it is a guaranteed-good local
# file we can upload, vs an already-ephemeral KIE tempfile URL.
# ----------------------------------------------------------------------
INFOGRAPHIC1_LOCAL=$(state_get '.infographic1LocalPath')

# Prefer the on-disk PNG (upload it) over a stale tempfile URL when available.
_inf1_src="$INFOGRAPHIC1_URL"
if [[ -n "$INFOGRAPHIC1_LOCAL" && "$INFOGRAPHIC1_LOCAL" != "null" && -s "$INFOGRAPHIC1_LOCAL" ]]; then
  _inf1_src="$INFOGRAPHIC1_LOCAL"
fi
# Preserve the ORIGINAL sources so an "image fetch failed" mid-job can re-host
# them to a fresh KIE URL and re-submit (see the retry loop below).
INF1_SRC_ORIG="$_inf1_src"
LOGO_SRC_ORIG="$LOGO_URL"

if [[ -n "$_inf1_src" && "$_inf1_src" != "null" ]]; then
  if _pub=$(ensure_public_url "$_inf1_src"); then
    log "INFO" "reference image infographic1 -> public URL: $_pub"
    INFOGRAPHIC1_URL="$_pub"
  else
    log "WARN" "reference image infographic1 could not be made public ('$_inf1_src'); OMITTING it from the video request (prompt-only render)"
    INFOGRAPHIC1_URL=""
  fi
else
  INFOGRAPHIC1_URL=""
fi

if [[ -n "$LOGO_URL" && "$LOGO_URL" != "null" ]]; then
  if _pub=$(ensure_public_url "$LOGO_URL"); then
    log "INFO" "reference image logo -> public URL: $_pub"
    LOGO_URL="$_pub"
  else
    log "WARN" "reference image logo could not be made public ('$LOGO_URL'); OMITTING it from the video request"
    LOGO_URL=""
  fi
fi

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
    # PRD step 4: default changed from 4 to 8 to meet the 8s floor requirement.
    case "$DURATION_INPUT" in
      4|5|6|7|8) DURATION="$DURATION_INPUT" ;;
      "")        DURATION="8" ;;
      *)
        log "WARN" "ZHC_VIDEO_DURATION='$DURATION_INPUT' is out of Gemini Omni range (4-8); falling back to 8"
        DURATION="8"
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
  # v10.X.4: KIE rejects requests without aspect_ratio with 422 "Aspect ratio
  # only supports [16:9, 9:16]". Always inject one. Env override is validated
  # to those two values to avoid round-tripping a 422 back to the operator.
  local aspect="${ZHC_CELEBRATION_VIDEO_ASPECT:-16:9}"
  case "$aspect" in
    16:9|9:16) ;;
    *)
      log "WARN" "ZHC_CELEBRATION_VIDEO_ASPECT='$aspect' not in [16:9, 9:16]; falling back to 16:9"
      aspect="16:9"
      ;;
  esac
  # KIE gemini-omni-video requires duration as a STRING ("8"), not an integer - returns error otherwise (verified 2026-05-27).
  # We use jq --arg (NOT --argjson) for duration so it is always emitted as a
  # quoted JSON string. aspect_ratio stays "16:9" (validated above).
  # PRD step 4: audio flag added to primary Gemini Omni body (was absent before,
  # only the Veo fallback had generate_audio). Logo URL composited when available.
  local input_obj
  # Build image_urls array: infographic first, then logo if available.
  # HARD RULE (Image-fetch fix): ONLY public http(s) URLs are ever placed here.
  # By this point ensure_public_url() has already converted file://, on-disk
  # paths, and flaky tempfile URLs into durable, model-reachable URLs (or emptied
  # them). This guard is belt-and-suspenders: any value that is not http(s) --
  # a file://, a bare path, an unknown scheme -- is NEVER sent to the model, so
  # the model can never be handed an unfetchable reference. (https is strongly
  # preferred; a plain-http public URL is still model-reachable, so we keep it
  # but warn.)
  local img_urls_arr="[]"
  _ref_ok() { [[ "$1" == https://* || "$1" == http://* ]]; }
  if _ref_ok "$INFOGRAPHIC1_URL"; then
    [[ "$INFOGRAPHIC1_URL" == http://* ]] && log "WARN" "submit: infographic reference is plain http (https preferred): $INFOGRAPHIC1_URL"
    img_urls_arr=$(jq -n --arg img "$INFOGRAPHIC1_URL" '[$img]')
  elif [[ -n "$INFOGRAPHIC1_URL" && "$INFOGRAPHIC1_URL" != "null" ]]; then
    log "WARN" "submit: dropping non-public infographic reference '$INFOGRAPHIC1_URL' (model cannot fetch it)"
  fi
  if _ref_ok "$LOGO_URL"; then
    [[ "$LOGO_URL" == http://* ]] && log "WARN" "submit: logo reference is plain http (https preferred): $LOGO_URL"
    img_urls_arr=$(echo "$img_urls_arr" | jq --arg logo "$LOGO_URL" '. + [$logo]')
  elif [[ -n "$LOGO_URL" && "$LOGO_URL" != "null" ]]; then
    log "WARN" "submit: dropping non-public logo reference '$LOGO_URL' (model cannot fetch it)"
  fi
  if [[ $(echo "$img_urls_arr" | jq 'length') -gt 0 ]]; then
    input_obj=$(jq -n \
      --arg prompt "$PROMPT" \
      --argjson imgs "$img_urls_arr" \
      --arg dur "$DURATION" \
      --arg aspect "$aspect" \
      '{prompt: $prompt, image_urls: $imgs, duration: $dur, aspect_ratio: $aspect, generate_audio: true}')
  else
    input_obj=$(jq -n \
      --arg prompt "$PROMPT" \
      --arg dur "$DURATION" \
      --arg aspect "$aspect" \
      '{prompt: $prompt, duration: $dur, aspect_ratio: $aspect, generate_audio: true}')
  fi
  local body
  body=$(jq -n \
    --arg model "$MODEL" \
    --argjson input "$input_obj" \
    '{model: $model, input: $input}')
  curl -sS --fail-with-body -X POST "$KIE_API_BASE/api/v1/jobs/createTask" \
    -H "Authorization: Bearer ${KIE_API_KEY:-}" \
    -H "Content-Type: application/json" \
    -d "$body"
}

poll_gemini_omni() {
  local task_id="$1"
  local elapsed=0
  local wait_sec
  local timeout_sec="${ZHC_VIDEO_POLL_TIMEOUT_SEC:-1800}"
  while (( elapsed < timeout_sec )); do
    local resp
    resp=$(curl -sS "$KIE_API_BASE/api/v1/jobs/recordInfo?taskId=$task_id" \
      -H "Authorization: Bearer ${KIE_API_KEY:-}" 2>/dev/null)
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
        # "Image fetch failed" (and kin) are TRANSIENT on the model side: the
        # backend couldn't pull a reference image this time. Signal the outer
        # retry loop (rc=2) so it RE-SUBMITS -- the references are already public
        # and get re-hosted to a fresh KIE URL on the next ensure step. Without
        # this, the recurring "Image fetch failed" across multiple recent closeouts
        # was a one-and-done hard fail.
        if echo "$msg" | grep -qiE 'image fetch failed|fetch.*image|failed to (fetch|download|load).*(image|url)|image.*(download|fetch).*fail'; then
          log "WARN" "Gemini Omni job $task_id: transient image-fetch failure ('$msg') -- signalling re-submit"
          return 2
        fi
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
  curl -sS --fail-with-body -X POST "$KIE_API_BASE/api/v1/veo/generate" \
    -H "Authorization: Bearer ${KIE_API_KEY:-}" \
    -H "Content-Type: application/json" \
    -d "$body"
}

poll_veo() {
  # v10.X.4: timeout 900 -> 1800 (env override ZHC_VIDEO_POLL_TIMEOUT_SEC).
  # errorCode/HTTP 500 mid-poll is now treated as transient (Veo upstream
  # blip), backoff 30s, up to 3 consecutive 500s before giving up.
  local task_id="$1"
  local elapsed=0
  local wait_sec
  local timeout_sec="${ZHC_VIDEO_POLL_TIMEOUT_SEC:-1800}"
  local consecutive_500=0
  while (( elapsed < timeout_sec )); do
    local resp http_code
    resp=$(curl -sS -w '\n__HTTP_CODE__%{http_code}' \
      "$KIE_API_BASE/api/v1/veo/record-info?taskId=$task_id" \
      -H "Authorization: Bearer ${KIE_API_KEY:-}" 2>/dev/null)
    http_code=$(printf '%s' "$resp" | awk -F'__HTTP_CODE__' 'END{print $2}')
    resp=$(printf '%s' "$resp" | sed 's/__HTTP_CODE__[0-9]*$//')

    # Pull body-level errorCode (KIE returns 200 HTTP but errorCode=500 inside
    # data when its upstream Veo provider has a transient hiccup).
    local body_err_code
    body_err_code=$(echo "$resp" | jq -r '.data.errorCode // .errorCode // empty' 2>/dev/null)

    # Treat HTTP 5xx OR body errorCode=500 as transient: backoff + retry.
    if { [[ -n "$http_code" && "$http_code" =~ ^5 ]] || [[ "$body_err_code" == "500" ]]; }; then
      consecutive_500=$((consecutive_500 + 1))
      if (( consecutive_500 > 3 )); then
        log "ERROR" "VEO poll: 4 consecutive transient 500s for $task_id; giving up"
        return 1
      fi
      log "WARN" "VEO poll got 500 (transient, attempt $consecutive_500/3), retrying in 30s"
      sleep 30
      elapsed=$((elapsed + 30))
      continue
    fi
    # Any other 4xx is terminal.
    if [[ -n "$http_code" && "$http_code" =~ ^4 ]]; then
      log "ERROR" "VEO poll HTTP $http_code for $task_id: $(echo "$resp" | head -c 200)"
      return 1
    fi
    consecutive_500=0

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
    log "INFO" "step=celebration-video poll for $task_id: in-progress (elapsed=${elapsed}s)"
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
# Inter-attempt backoff base (seconds): sleep grows as BASE**attempt. Overridable
# so the test harness can run with no real waits; production keeps 4 (4s,16s,64s).
ZHC_VIDEO_RETRY_BACKOFF_BASE="${ZHC_VIDEO_RETRY_BACKOFF_BASE:-4}"
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
  poll_rc=0
  case "$MODEL" in
    gemini-omni-video)
      submit_resp=$(submit_gemini_omni || true)
      task_id=$(echo "$submit_resp" | jq -r '.data.taskId // .taskId // empty' 2>/dev/null)
      if [[ -n "$task_id" ]]; then
        log "INFO" "attempt $attempt: submitted gemini-omni-video taskId=$task_id"
        result_url=$(poll_gemini_omni "$task_id"); poll_rc=$?
        # rc=2 -> transient "image fetch failed": the model couldn't pull a
        # reference. Re-host the ORIGINAL references to brand-new public KIE URLs
        # so the next submit hands the model fresh, definitely-fetchable URLs.
        if (( poll_rc == 2 )); then
          log "WARN" "attempt $attempt: image-fetch transient; re-hosting references to fresh public URLs before re-submit"
          if [[ -n "$INF1_SRC_ORIG" && "$INF1_SRC_ORIG" != "null" ]]; then
            if _pub=$(ensure_public_url "$INF1_SRC_ORIG"); then INFOGRAPHIC1_URL="$_pub"; else INFOGRAPHIC1_URL=""; fi
          fi
          if [[ -n "$LOGO_SRC_ORIG" && "$LOGO_SRC_ORIG" != "null" ]]; then
            if _pub=$(ensure_public_url "$LOGO_SRC_ORIG"); then LOGO_URL="$_pub"; else LOGO_URL=""; fi
          fi
          result_url=""
        fi
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
    sleep $(( ZHC_VIDEO_RETRY_BACKOFF_BASE ** attempt ))
    continue
  fi
  if [[ -n "$result_url" && "$result_url" != "null" ]]; then
    log "INFO" "attempt $attempt: success remote-url=$result_url"
    break
  fi
  log "WARN" "attempt $attempt: did not produce a usable URL"
  result_url=""
  sleep $(( ZHC_VIDEO_RETRY_BACKOFF_BASE ** attempt ))
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
