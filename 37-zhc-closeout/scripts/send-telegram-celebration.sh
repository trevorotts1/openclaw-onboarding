#!/usr/bin/env bash
# send-telegram-celebration.sh -- 6-message paced Telegram delivery to the owner.
#
# Tracks per-message delivery in state.messagesDelivered = [1,2,3,4,5,6].
# Each message is idempotent -- re-running only sends messages not yet in the
# delivered list. On per-message exhaustion, marks failure but continues.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[telegram] no OpenClaw root" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
STEP_LABEL="telegram"

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2"
}
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }

OWNER_CHAT=$(state_get '.ownerChat')
OWNER_NAME=$(state_get '.ownerName'); [[ -z "$OWNER_NAME" ]] && OWNER_NAME="there"
COMPANY_NAME=$(state_get '.companyName'); [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="your company"
AGENT_NAME=$(state_get '.agentName'); [[ -z "$AGENT_NAME" ]] && AGENT_NAME="your CEO Agent"
N_DEPTS=$(jq -r '[.departments[] | select(.status == "done")] | length' "$STATE_FILE")
N_ROLES=$(jq -r '[.departments[].rolesDone // 0] | add' "$STATE_FILE")
INFO_1=$(state_get '.infographic1Url')
INFO_1_LOCAL=$(state_get '.infographic1LocalPath')
INFO_2=$(state_get '.infographic2Url')
VIDEO=$(state_get '.celebrationVideoUrl')
VIDEO_LOCAL=$(state_get '.celebrationVideoLocalPath')
NOTION_URL=$(state_get '.notionRootPageUrl')
CC_URL=$(state_get '.commandCenterUrl')
# v10.x: shareable Convert and Flow / GHL media-library link (set by run-closeout
# STEP 5.5 via upload-ghl-media.sh). Empty when the client has no GHL location.
GHL_MEDIA_URL="${ZHC_GHL_MEDIA_URL:-$(state_get '.ghlMediaLibraryUrl')}"

if [[ -z "$OWNER_CHAT" || "$OWNER_CHAT" == "null" ]]; then
  log "ERROR" "ownerChat missing from state -- cannot deliver"
  exit 1
fi

# Initialize messagesDelivered if not present
if ! jq -e '.messagesDelivered' "$STATE_FILE" >/dev/null 2>&1; then
  state_set '.messagesDelivered = []'
fi

is_delivered() {
  local n="$1"
  jq -e --argjson n "$n" '.messagesDelivered | index($n) != null' "$STATE_FILE" >/dev/null 2>&1
}
mark_delivered() {
  local n="$1"
  state_set ".messagesDelivered = (.messagesDelivered + [$n] | unique)"
}

# Send a text message with retry. Returns 0 on success.
send_text() {
  local text="$1"
  local attempt=0
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    if openclaw message send --channel telegram -t "$OWNER_CHAT" -m "$text" >> "$LOG_FILE" 2>&1; then
      return 0
    fi
    log "WARN" "send_text attempt $attempt failed"
    sleep $((2 ** attempt))
  done
  return 1
}

# Send a photo with caption. Prefers a LOCAL file path (uploaded via --media
# as multipart bytes) over a remote URL when both are available -- this is
# how we guarantee Telegram inlines the image instead of treating it as a
# download card (Lesson 2 from the Marico closeout).
send_photo() {
  local url="$1"
  local caption="$2"
  local local_path="${3:-}"
  local attempt=0
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    # Prefer local file bytes via --media (multipart upload).
    if [[ -n "$local_path" && -s "$local_path" ]]; then
      if openclaw message send --channel telegram -t "$OWNER_CHAT" --media "$local_path" -m "$caption" >> "$LOG_FILE" 2>&1; then
        return 0
      fi
    fi
    # Fall back to --photo URL if --media unavailable / no local copy.
    if [[ -n "$url" && "$url" != null && "$url" != file://* ]]; then
      if openclaw message send --channel telegram -t "$OWNER_CHAT" --photo "$url" -m "$caption" >> "$LOG_FILE" 2>&1; then
        return 0
      fi
    fi
    # Last resort: send caption + URL as plain text (skip if URL is file://).
    if [[ -n "$url" && "$url" != file://* ]]; then
      if openclaw message send --channel telegram -t "$OWNER_CHAT" -m "${caption}

${url}" >> "$LOG_FILE" 2>&1; then
        return 0
      fi
    fi
    log "WARN" "send_photo attempt $attempt failed"
    sleep $((2 ** attempt))
  done
  return 1
}

# CRITICAL (Lesson 2 from Marico closeout): NEVER pass tempfile.aiquickdraw.com
# URLs directly to Telegram. The CDN returns content-disposition: attachment,
# so Telegram renders the message as a download card rather than an inline
# video player. generate-celebration-video.sh ALWAYS downloads the MP4 bytes
# to disk first and writes .celebrationVideoLocalPath into state -- we send
# THOSE bytes here via --media so the bot uploads via Telegram's multipart
# sendVideo endpoint, which embeds inline.
send_video() {
  local url="$1"
  local caption="$2"
  local local_path="${3:-}"
  local attempt=0
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    if [[ -n "$local_path" && -s "$local_path" ]]; then
      if openclaw message send --channel telegram -t "$OWNER_CHAT" --media "$local_path" -m "$caption" >> "$LOG_FILE" 2>&1; then
        return 0
      fi
    fi
    if [[ -n "$url" && "$url" != null && "$url" != file://* ]]; then
      if openclaw message send --channel telegram -t "$OWNER_CHAT" --video "$url" -m "$caption" >> "$LOG_FILE" 2>&1; then
        return 0
      fi
    fi
    if [[ -n "$url" && "$url" != file://* ]]; then
      if openclaw message send --channel telegram -t "$OWNER_CHAT" -m "${caption}

${url}" >> "$LOG_FILE" 2>&1; then
        return 0
      fi
    fi
    log "WARN" "send_video attempt $attempt failed"
    sleep $((2 ** attempt))
  done
  return 1
}

failed_messages=()

# ---- Message 1: Announcement ----
if is_delivered 1; then
  log "INFO" "msg 1: already delivered -- skipping"
else
  log "INFO" "msg 1: sending announcement"
  MSG1="🎉 ${OWNER_NAME}, your zero-human company is built.

Over the past few hours your AI workforce has been getting itself set up.
${N_DEPTS} departments. ${N_ROLES} AI employees. All hired, briefed, and ready to work for you.

Here's what I want to show you:"
  if send_text "$MSG1"; then
    mark_delivered 1
    log "INFO" "msg 1: delivered"
    sleep 10
  else
    log "ERROR" "msg 1: FAILED after 3 attempts -- aborting (no point sending celebration if announcement didn't land)"
    state_set '.closeoutStatus = "failed" | .closeoutFailureReason = "telegram-message-1: 3 retries exhausted"'
    exit 1
  fi
fi

# ---- Message 2: Infographic #1 ----
if is_delivered 2; then
  log "INFO" "msg 2: already delivered -- skipping"
elif [[ ( -z "$INFO_1" || "$INFO_1" == "null" ) && ( -z "$INFO_1_LOCAL" || ! -s "$INFO_1_LOCAL" ) ]]; then
  log "WARN" "msg 2: infographic1Url and infographic1LocalPath both missing -- skipping"
  failed_messages+=("msg-2-no-url")
else
  log "INFO" "msg 2: sending infographic #1"
  if send_photo "$INFO_1" "📊 Your workforce structure -- how your AI company is organized." "$INFO_1_LOCAL"; then
    mark_delivered 2
    log "INFO" "msg 2: delivered"
    sleep 5
  else
    log "ERROR" "msg 2: FAILED -- continuing"
    failed_messages+=("msg-2")
  fi
fi

# ---- Message 3: Infographic #2 ----
if is_delivered 3; then
  log "INFO" "msg 3: already delivered -- skipping"
elif [[ -z "$INFO_2" || "$INFO_2" == "null" ]]; then
  log "WARN" "msg 3: infographic2Url missing -- skipping"
  failed_messages+=("msg-3-no-url")
else
  log "INFO" "msg 3: sending infographic #2"
  if send_photo "$INFO_2" "⚙️ How the work flows -- from a task you give me, all the way to a finished output."; then
    mark_delivered 3
    log "INFO" "msg 3: delivered"
    sleep 5
  else
    log "ERROR" "msg 3: FAILED -- continuing"
    failed_messages+=("msg-3")
  fi
fi

# ---- Message 4: Celebration video ----
#
# v10.X.4: when video generation failed (ZHC_VIDEO_STATUS=failed exported by
# run-closeout.sh), send a text-only "deferred" notice in slot 4 instead of
# silently skipping. The closeout still completes as `partial` so the resume
# cron will re-attempt the video tonight when vendor congestion clears.
if is_delivered 4; then
  log "INFO" "msg 4: already delivered -- skipping"
elif [[ "${ZHC_VIDEO_STATUS:-}" == "failed" ]]; then
  log "INFO" "msg 4: video generation failed upstream -- sending text-only deferred notice"
  MSG4_DEFERRED="🎬 Your celebration video is queued but deferred for tonight -- the video vendor is hitting congestion right now. It'll show up in this thread automatically when it lands. Everything else below is ready to go."
  if send_text "$MSG4_DEFERRED"; then
    mark_delivered 4
    log "INFO" "msg 4: deferred-notice delivered"
    sleep 4
  else
    log "ERROR" "msg 4: FAILED -- continuing"
    failed_messages+=("msg-4")
  fi
elif [[ ( -z "$VIDEO" || "$VIDEO" == "null" ) && ( -z "$VIDEO_LOCAL" || ! -s "$VIDEO_LOCAL" ) ]]; then
  log "WARN" "msg 4: celebrationVideoUrl and celebrationVideoLocalPath both missing -- skipping"
  failed_messages+=("msg-4-no-url")
else
  log "INFO" "msg 4: sending celebration video"
  if send_video "$VIDEO" "🎬 A quick celebration -- congratulations on launching ${COMPANY_NAME}'s zero-human workforce." "$VIDEO_LOCAL"; then
    mark_delivered 4
    log "INFO" "msg 4: delivered"
    sleep 8
  else
    log "ERROR" "msg 4: FAILED -- continuing"
    failed_messages+=("msg-4")
  fi
fi

# ---- Message 5: Notion doc link ----
if is_delivered 5; then
  log "INFO" "msg 5: already delivered -- skipping"
elif [[ -z "$NOTION_URL" || "$NOTION_URL" == "null" ]]; then
  log "WARN" "msg 5: notionRootPageUrl missing -- skipping"
  failed_messages+=("msg-5-no-url")
else
  log "INFO" "msg 5: sending Notion doc link"
  MSG5="📕 Your full closeout doc is in your Notion workspace:
${NOTION_URL}

It explains your departments, your AI employees, the communication hierarchy, the Six Sigma framework we'll use to keep improving, the Book-to-Persona system that picks how each task is handled, and your First 7 Days action plan. Read it when you have 15 minutes."
  if send_text "$MSG5"; then
    mark_delivered 5
    log "INFO" "msg 5: delivered"
    sleep 3
  else
    log "ERROR" "msg 5: FAILED -- continuing"
    failed_messages+=("msg-5")
  fi
fi

# ---- Message 6: Command Center URL ----
#
# Hardened against the v3-era bugs that hit Lyric + Evelyn:
#   - commandCenterUrl was null (Lyric) → we'd have sent an empty URL line
#   - commandCenterUrl was the legacy fake http://localhost:4000 (Evelyn) →
#     useless to the client; their dashboard lives at a public CF tunnel URL.
# Real public URL must start with https:// AND not be localhost.
cc_url_is_real() {
  local u="$1"
  [[ -z "$u" || "$u" == "null" ]] && return 1
  [[ "$u" == "http://localhost:4000" || "$u" == "http://localhost:4000/" ]] && return 1
  [[ "$u" != https://* ]] && return 1
  # reject any localhost host even under https://
  [[ "$u" == https://localhost* ]] && return 1
  return 0
}

CC_BOOKMARK_FILE="$OC_ROOT/workspace/.zhc-dashboard-url"

if is_delivered 6; then
  log "INFO" "msg 6: already delivered -- skipping"
elif ! cc_url_is_real "$CC_URL"; then
  log "WARN" "msg 6: commandCenterUrl missing or local-only -- skipping Command Center URL message"
  failed_messages+=("msg-6-no-url")
else
  log "INFO" "msg 6: sending Command Center URL"
  # v10.x: append the Convert and Flow media-library link if the closeout media
  # was uploaded to the client's GHL location (org chart + video + infographics).
  GHL_MEDIA_LINE=""
  if [[ -n "$GHL_MEDIA_URL" && "$GHL_MEDIA_URL" == https://* ]]; then
    GHL_MEDIA_LINE="

📁 Your celebration video and graphics are also in your Convert and Flow media library:
${GHL_MEDIA_URL}"
  fi
  MSG6="🎛️ Your BlackCEO Command Center:
${CC_URL}

This is where you'll talk to your CEO (${AGENT_NAME}), watch tasks move across the Kanban board, and check in on every department. Open it in your browser and bookmark it.${GHL_MEDIA_LINE}

When you're ready, just message me with the first thing you want done. I'm standing by.

-- ${AGENT_NAME}"
  if send_text "$MSG6"; then
    mark_delivered 6
    log "INFO" "msg 6: delivered"
    # Persist the URL to a local bookmark file for recovery.
    if printf '%s\n' "$CC_URL" > "$CC_BOOKMARK_FILE" 2>>"$LOG_FILE"; then
      chmod 600 "$CC_BOOKMARK_FILE" 2>>"$LOG_FILE" || true
      log "INFO" "msg 6: bookmark file written at $CC_BOOKMARK_FILE"
    else
      log "WARN" "msg 6: failed to write bookmark file at $CC_BOOKMARK_FILE"
    fi
    sleep 3
  else
    log "ERROR" "msg 6: FAILED -- continuing"
    failed_messages+=("msg-6")
  fi
fi

# ---- Message 7: Dashboard bookmark recovery hint ----
# Always emitted after the URL attempt (success OR skip), so the client knows
# where to look for the URL even if the Telegram message scrolls away or msg 6
# was skipped due to a missing/local URL.
if is_delivered 7; then
  log "INFO" "msg 7: already delivered -- skipping"
else
  log "INFO" "msg 7: sending bookmark hint"
  MSG7="🔖 Your dashboard URL has been bookmarked at \`${CC_BOOKMARK_FILE}\`. If you ever lose this message, that file has it.

-- ${AGENT_NAME}"
  if send_text "$MSG7"; then
    mark_delivered 7
    log "INFO" "msg 7: delivered"
  else
    log "ERROR" "msg 7: FAILED -- continuing"
    failed_messages+=("msg-7")
  fi
fi

# ---- summary ----
if (( ${#failed_messages[@]} == 0 )); then
  state_set '.closeoutStatus = "sent"'
  log "INFO" "all messages delivered -- closeoutStatus=sent"
  exit 0
else
  reason="telegram-partial: $(IFS=,; echo "${failed_messages[*]}")"
  state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\""
  log "ERROR" "delivery partial; failed: ${failed_messages[*]}"
  exit 1
fi
