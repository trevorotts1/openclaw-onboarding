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
#
#   FALLBACK: Veo 3.1 via KIE.ai (model slug: veo3 or veo3_fast).
#     Veo 3.1 / veo3_fast is the GENERAL-PURPOSE default video model
#     elsewhere in OpenClaw - it just isn't ideal for *this* celebration
#     use case because Veo3 cannot accept an image guidance reference.
#
# KIE transport: every call (upload, createTask, poll, download) is Skill 74's CLI via lib-kie74.sh; Skill 74
# submits to the path each model's schema declares. If Skill 74 is not installed this script stops with a clear
# error. The veo3 / veo3_fast fallback therefore needs a model whose schema Skill 74 can read.
#
# Env overrides:
#   ZHC_CELEBRATION_VIDEO_MODEL  default: gemini-omni-video
#                                accepts:  gemini-omni-video | veo3 | veo3_fast
#   ZHC_VIDEO_DURATION           default: 8 (Gemini Omni and Veo)
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
#     - file:// or on-disk path -> KIE upload (Skill 74 `upload --file`)
#     - existing http(s) URL     -> KIE re-host (Skill 74 `upload --url`), so an expired
#                                   or flaky tempfile becomes a fresh KIE-hosted
#                                   URL the model can fetch.
#   Both uploaders retry-with-backoff. submit_gemini_omni()/poll also treat
#   "image fetch failed" as a transient and retry. Uploaded files are
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
# SK1-15: isolate the rendered video per client. run-closeout.sh's lock is
# per-slug so different clients run concurrently; a fixed .zhc-celebration-video.mp4
# let one client's render overwrite another's, shipping the wrong video. Key the
# path on the same slug run-closeout.sh locks on (direct jq — state_get is defined
# further down).
_client_slug="$(jq -r '.companySlug // .companyName // empty' "$STATE_FILE" 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-*//; s/-*$//')"
[[ -z "$_client_slug" ]] && _client_slug="default"
LOCAL_MP4="$OC_ROOT/workspace/.zhc-celebration-video.${_client_slug}.mp4"

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  # Console copy goes to STDERR, never STDOUT. Several helpers below have their
  # STDOUT captured by command substitution (submit_*, poll_*, ensure_public_url,
  # _upload_*). Logging to stdout would poison those captures (e.g. a warning line
  # interleaved into the createTask JSON response broke task_id extraction).
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >&2
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

# One KIE path: Skill 74 (upload, createTask, poll, download). See lib-kie74.sh.
# shellcheck source=lib-kie74.sh disable=SC1090,SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-kie74.sh"

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
# Uploads and re-hosting go through Skill 74 (`upload --file` / `upload --url`, KIE temp-file service,
# durable ~3 day KIE-hosted https URL). KIE_UPLOAD_BASE / KIE_API_BASE remain test hooks only (lib-kie74.sh
# maps them to Skill 74's localhost-only KIE_LIVE_* hooks, so a harness can point the pipeline at a local mock).
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

# _upload_local_to_public <disk_path> -> echoes a public KIE URL (Skill 74 upload), or non-zero.
_upload_local_to_public() { kie74_upload_file "$(_local_to_disk "$1")"; }

# _rehost_url_to_public <http_url> -> echoes a fresh KIE-hosted URL (Skill 74 upload --url), or non-zero.
_rehost_url_to_public() { kie74_upload_url "$1"; }

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

# FIX-S36-03 (idempotency guard): this generator is now invoked through
# run-closeout.sh's generate_rate_gate, which ALWAYS calls it (the old Step-4
# `celebrationVideoUrl already set` short-circuit was removed when the video was
# brought under the 8.5 gate). To avoid RE-SPENDING on the paid Veo/KIE backend
# on every resume-cron re-entry, self-skip when the video is already produced:
# a non-null celebrationVideoUrl AND a non-empty local mp4 on disk. The gate then
# rates the existing artifact instead of regenerating it. Mirrors the infographic
# generators' own "already populated -> skip" idempotency.
_existing_video_url=$(state_get '.celebrationVideoUrl')
if [[ -n "$_existing_video_url" && "$_existing_video_url" != "null" && -s "$LOCAL_MP4" ]]; then
  log "INFO" "celebration video already produced (url set + $LOCAL_MP4 present) -- skipping regeneration (idempotent; no paid re-spend)"
  exit 0
fi

# Skill 74 is required from here on (the idempotent skip above does not need it).
kie74_locate || exit 1

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
# Request: Gemini Omni Video (default) or Veo 3.x (general-purpose fallback). Skill 74 runs it:
# validate against the model's live schema, submit to the path that schema declares, poll, save.
# ----------------------------------------------------------------------
build_request_gemini_omni() {
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
  jq -n --arg model "$MODEL" --argjson input "$input_obj" '{model: $model, input: $input}'
}

build_request_veo() {
  jq -n \
    --arg model "$MODEL" \
    --arg prompt "$PROMPT" \
    --argjson duration "$DURATION" \
    '{model: $model, input: {prompt: $prompt, aspect_ratio: "9:16", duration: $duration, generate_audio: true}}'
}

# run_video_job <request_json>: Skill 74 `run` (submit, wait, save the MP4). Sets JOB_JSON and
# result_url / task_id. Returns 0 on success, 2 on a transient "image fetch failed" (caller re-hosts and
# re-submits), 1 otherwise.
run_video_job() {
  local req_file="$1" msg
  JOB_DIR="$(mktemp -d "${TMPDIR:-/tmp}/zhc-video-job.XXXXXX")"
  JOB_JSON=""
  if JOB_JSON=$(kie74_run "$req_file" "$JOB_DIR" "${ZHC_VIDEO_POLL_TIMEOUT_SEC:-1800}"); then
    return 0
  fi
  msg=$(_kie74_error "$JOB_JSON")
  # "Image fetch failed" (and kin) are TRANSIENT on the model side: the backend couldn't pull a reference
  # image this time. Signal the outer retry loop (rc=2) so it RE-SUBMITS -- the references are already
  # public and get re-hosted to a fresh KIE URL on the next ensure step.
  if echo "$msg" | grep -qiE 'image fetch failed|fetch.*image|failed to (fetch|download|load).*(image|url)|image.*(download|fetch).*fail'; then
    log "WARN" "$MODEL job: transient image-fetch failure ('$msg') -- signalling re-submit"
    return 2
  fi
  log "ERROR" "$MODEL job failed: $msg"
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
SAVED_MP4=""
while (( attempt < 3 )); do
  attempt=$((attempt + 1))
  if (( attempt == 3 )) && [[ "$MODEL" == "gemini-omni-video" ]]; then
    MODEL="veo3_fast"
    DURATION="8"
    log "INFO" "attempt $attempt: falling back to $MODEL (general-purpose video default)"
  fi

  log "INFO" "attempt $attempt/3: submitting video job model=$MODEL duration=${DURATION}s (Skill 74)"
  REQ_FILE="$(mktemp "${TMPDIR:-/tmp}/zhc-video-req.XXXXXX")"
  case "$MODEL" in
    gemini-omni-video) build_request_gemini_omni > "$REQ_FILE" ;;
    veo3|veo3_fast)    build_request_veo > "$REQ_FILE" ;;
  esac
  run_video_job "$REQ_FILE"; job_rc=$?
  rm -f "$REQ_FILE"
  if (( job_rc == 0 )); then
    result_url=$(printf '%s' "$JOB_JSON" | jq -r '.result_urls[0] // empty' 2>/dev/null)
    SAVED_MP4=$(printf '%s' "$JOB_JSON" | jq -r '.saved_paths[0] // empty' 2>/dev/null)
  elif (( job_rc == 2 )) && [[ "$MODEL" == "gemini-omni-video" ]]; then
    # rc=2 -> transient "image fetch failed": the model couldn't pull a reference. Re-host the ORIGINAL
    # references to brand-new public KIE URLs so the next submit hands the model fresh, fetchable URLs.
    log "WARN" "attempt $attempt: image-fetch transient; re-hosting references to fresh public URLs before re-submit"
    if [[ -n "$INF1_SRC_ORIG" && "$INF1_SRC_ORIG" != "null" ]]; then
      if _pub=$(ensure_public_url "$INF1_SRC_ORIG"); then INFOGRAPHIC1_URL="$_pub"; else INFOGRAPHIC1_URL=""; fi
    fi
    if [[ -n "$LOGO_SRC_ORIG" && "$LOGO_SRC_ORIG" != "null" ]]; then
      if _pub=$(ensure_public_url "$LOGO_SRC_ORIG"); then LOGO_URL="$_pub"; else LOGO_URL=""; fi
    fi
  fi

  if [[ -n "$result_url" && "$result_url" != "null" && -s "$SAVED_MP4" ]]; then
    log "INFO" "attempt $attempt: success remote-url=$result_url"
    break
  fi
  log "WARN" "attempt $attempt: did not produce a usable video"
  result_url=""
  rm -rf "${JOB_DIR:-/nonexistent-zhc}" 2>/dev/null
  sleep $(( ZHC_VIDEO_RETRY_BACKOFF_BASE ** attempt ))
done

if [[ -z "$result_url" ]]; then
  log "ERROR" "all attempts exhausted; no celebration video produced"
  exit 1
fi

# ----------------------------------------------------------------------
# CRITICAL: the MP4 bytes must be on disk so the Telegram step can upload.
# (Telegram cannot inline-render a tempfile.aiquickdraw.com URL because the
# CDN serves it with content-disposition: attachment.) Skill 74 already saved the file; move it into place.
# ----------------------------------------------------------------------
log "INFO" "placing celebration video bytes at $LOCAL_MP4"
if ! mv -f "$SAVED_MP4" "$LOCAL_MP4"; then
  log "ERROR" "failed to place the saved celebration video at $LOCAL_MP4"
  exit 1
fi
rm -rf "${JOB_DIR:-/nonexistent-zhc}" 2>/dev/null
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
