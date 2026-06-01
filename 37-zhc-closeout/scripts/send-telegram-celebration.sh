#!/usr/bin/env bash
# send-telegram-celebration.sh -- 6-message paced Telegram delivery to the owner.
#
# DELIVERY CONFIRMATION (anti-faking, hardened):
#   `openclaw message send` can exit 0 while the message never reached Telegram
#   (silent Telegram-offset-corruption; fresh-VPS "scope upgrade pending
#   approval"). Exit-code-only "delivery" is therefore a LIE waiting to happen.
#   So every send here captures the REAL gateway messageId (`--json` -> .messageId,
#   with a best-effort stdout parse fallback) and a message is only counted
#   delivered when a NON-EMPTY messageId comes back.
#
#   state.messagesDelivered is an ARRAY OF OBJECTS:
#     { "n": <slot 1-7>, "messageId": "<id>", "chatId": "<owner chat>", "ts": "<iso>" }
#   A send that returns no messageId records { "n": <slot>, "status": "send-failed" }
#   and is NOT counted delivered. Idempotent -- re-running only sends slots not
#   yet confirmed-delivered (a slot with status:"send-failed" is retried).
#
#   The captured messageIds are later cross-checked against the gateway
#   sent-registry by verify-telegram-delivery.sh (invoked from run-closeout.sh)
#   before the closeout may be marked done. THIS script proves "the gateway
#   accepted and returned an id"; verify-telegram-delivery.sh proves "the id is
#   actually in the sent-registry". Both layers must pass.

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
# v10.x: per-artifact REAL public URLs from the GHL media upload
# (storage.googleapis.com/msgsndr/... -- openable without a GHL login). These are
# the DURABLE openable links posted alongside each artifact so a real link is in
# the message even after the inline Telegram media ages out of view. Empty when
# the client has no GHL location or the upload was skipped.
GHL_VIDEO_PUBLIC_URL=$(state_get '.ghlVideoPublicUrl')
GHL_INF1_PUBLIC_URL=$(state_get '.ghlInfographic1PublicUrl')
GHL_INF2_PUBLIC_URL=$(state_get '.ghlInfographic2PublicUrl')

# openable_link <ghl-public-url> <kie-remote-url> -- choose the best REAL,
# openable link for an artifact: prefer the durable GHL public URL, fall back to
# the (ephemeral) KIE/remote URL, and emit nothing for a file:// or empty value.
openable_link() {
  local ghl="$1" remote="$2"
  if [[ -n "$ghl" && "$ghl" == https://* ]]; then printf '%s' "$ghl"; return 0; fi
  if [[ -n "$remote" && "$remote" != "null" && "$remote" == http* && "$remote" != file://* ]]; then
    printf '%s' "$remote"; return 0
  fi
  printf ''
}

if [[ -z "$OWNER_CHAT" || "$OWNER_CHAT" == "null" ]]; then
  log "ERROR" "ownerChat missing from state -- cannot deliver"
  exit 1
fi

# Initialize messagesDelivered if not present (array of objects).
if ! jq -e '.messagesDelivered' "$STATE_FILE" >/dev/null 2>&1; then
  state_set '.messagesDelivered = []'
fi

# ----------------------------------------------------------------------
# Delivery bookkeeping -- objects, not bare integers.
# A slot is "delivered" ONLY when it has a non-empty messageId recorded.
# ----------------------------------------------------------------------
is_delivered() {
  local n="$1"
  jq -e --argjson n "$n" \
    '(.messagesDelivered // []) | any(.[]; (.n == $n) and ((.messageId // "") | tostring | length > 0))' \
    "$STATE_FILE" >/dev/null 2>&1
}

# record_delivered <n> <messageId> -- store a confirmed delivery object. Removes
# any prior placeholder/failed record for the same slot first (so a retried slot
# is upgraded from send-failed to delivered).
record_delivered() {
  local n="$1" mid="$2" ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  state_set "
    .messagesDelivered = ((.messagesDelivered // []) | map(select(.n != $n)))
    + [{\"n\": $n, \"messageId\": \"$mid\", \"chatId\": \"$OWNER_CHAT\", \"ts\": \"$ts\"}]
  "
}

# record_failed <n> <reason> -- record a non-delivered slot (no messageId). Does
# NOT overwrite an already-confirmed delivery for that slot.
record_failed() {
  local n="$1" reason="${2:-no-messageId}" ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if is_delivered "$n"; then return 0; fi
  state_set "
    .messagesDelivered = ((.messagesDelivered // []) | map(select(.n != $n)))
    + [{\"n\": $n, \"status\": \"send-failed\", \"reason\": \"$reason\", \"chatId\": \"$OWNER_CHAT\", \"ts\": \"$ts\"}]
  "
}

# ----------------------------------------------------------------------
# extract_message_id <raw-output> -- pull a real Telegram messageId out of an
# `openclaw message send --json` result. Tries, in order:
#   1. JSON .messageId        (top-level, current 2026.5.x shape)
#   2. JSON .payload.messageId
#   3. JSON .result.messageId / .data.messageId (defensive for shape drift)
#   4. best-effort regex on raw text  ("messageId":"123" or messageId: 123)
# Prints the id on success (empty on failure). Never trusts ok:true alone -- a
# non-empty id is mandatory.
# ----------------------------------------------------------------------
extract_message_id() {
  local raw="$1" mid="" jq_expr='(.messageId // .payload.messageId // .result.messageId // .data.messageId // empty) | tostring'
  # 1) Clean --json output IS a valid JSON document -- parse the raw output first.
  mid=$(printf '%s' "$raw" | jq -r "$jq_expr" 2>/dev/null)
  # 2) If the gateway wrapped the JSON in log noise, isolate the object and retry.
  if [[ -z "$mid" || "$mid" == "null" ]]; then
    local json
    json=$(printf '%s' "$raw" | sed -n '/{/,/}/p' 2>/dev/null)
    [[ -n "$json" ]] && mid=$(printf '%s' "$json" | jq -r "$jq_expr" 2>/dev/null)
  fi
  # 3) Best-effort regex fallback for installs where --json is absent/garbled.
  #    Require a non-empty id; never regress to exit-code-only.
  if [[ -z "$mid" || "$mid" == "null" ]]; then
    mid=$(printf '%s' "$raw" | grep -oE '"messageId"[[:space:]]*:[[:space:]]*"?[0-9]+"?' | head -1 | grep -oE '[0-9]+' | head -1)
    [[ -z "$mid" ]] && mid=$(printf '%s' "$raw" | grep -oiE 'message[_ ]?id[[:space:]]*[:=][[:space:]]*"?[0-9]+' | head -1 | grep -oE '[0-9]+' | head -1)
  fi
  [[ "$mid" == "null" ]] && mid=""
  printf '%s' "$mid"
}

# ----------------------------------------------------------------------
# do_send <slot-n> <build-the-args-fn> -- generic confirmed sender.
# Calls `openclaw message send --json <args...>`, extracts a real messageId,
# and on a NON-EMPTY id records the delivery + returns 0. Retries with backoff.
# Returns 1 (and the caller records a failed slot) if no id ever comes back.
#
# The args are produced by a per-message builder passed as remaining params,
# so text/photo/video share identical confirmation logic.
# ----------------------------------------------------------------------
_oc_send_json() {
  # _oc_send_json <args...> -- run the send, echo raw output, return cmd rc.
  openclaw message send --json --channel telegram -t "$OWNER_CHAT" "$@" 2>&1
}

# send_confirmed <slot-n> <send-arg> ... -- args after slot-n are passed verbatim
# to `openclaw message send`. Returns 0 only when a real messageId is captured
# AND recorded. Logs the captured id.
send_confirmed() {
  local n="$1"; shift
  local attempt=0 raw mid rc
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    raw=$(_oc_send_json "$@"); rc=$?
    printf '%s\n' "$raw" >> "$LOG_FILE"
    if (( rc == 0 )); then
      mid=$(extract_message_id "$raw")
      if [[ -n "$mid" ]]; then
        record_delivered "$n" "$mid"
        log "INFO" "msg $n: gateway returned messageId=$mid (attempt $attempt) -- recorded delivered"
        return 0
      fi
      log "WARN" "msg $n: send exited 0 but NO messageId in result (attempt $attempt) -- NOT counting delivered"
    else
      log "WARN" "msg $n: send rc=$rc (attempt $attempt)"
    fi
    sleep $((2 ** attempt))
  done
  return 1
}

# Build a TEXT send for slot n. Returns 0 on confirmed delivery.
send_text() {
  local n="$1" text="$2"
  send_confirmed "$n" -m "$text"
}

# Build a PHOTO send for slot n. Prefers LOCAL bytes via --media (multipart) over
# a remote URL (Lesson 2: inline image, not a download card), then falls back to
# --photo URL, then caption+URL text. Each variant goes through send_confirmed so
# a real messageId is required regardless of which path lands.
#
# v10.x: arg 5 = a durable openable link (the GHL public URL). When present it is
# appended to the caption as an "Open it directly:" line so a REAL openable link
# rides along with the inline image -- not just an image the client can't re-find.
send_photo() {
  local n="$1" url="$2" caption="$3" local_path="${4:-}" open_link="${5:-}"
  local cap="$caption"
  [[ -n "$open_link" && "$open_link" == https://* ]] && cap="${caption}

🔗 Open it directly: ${open_link}"
  if [[ -n "$local_path" && -s "$local_path" ]]; then
    send_confirmed "$n" --media "$local_path" -m "$cap" && return 0
  fi
  if [[ -n "$url" && "$url" != null && "$url" != file://* ]]; then
    send_confirmed "$n" --photo "$url" -m "$cap" && return 0
  fi
  # text-only fallback: caption + whatever openable link we have (GHL or remote).
  local link
  link=$(openable_link "$open_link" "$url")
  if [[ -n "$link" ]]; then
    send_confirmed "$n" -m "${caption}

🔗 ${link}" && return 0
  fi
  return 1
}

# Build a VIDEO send for slot n. Prefers LOCAL bytes via --media (multipart
# sendVideo, inline) over --video URL, then caption+URL text. (Lesson 2:
# tempfile.aiquickdraw.com URLs render as download cards, so video bytes are
# downloaded to disk by generate-celebration-video.sh and sent here.)
#
# v10.x: arg 5 = a durable openable link (the GHL public URL). Appended to the
# caption as an "Open it directly:" line so the celebration video always carries
# a REAL openable link even after the inline player ages out of the thread.
send_video() {
  local n="$1" url="$2" caption="$3" local_path="${4:-}" open_link="${5:-}"
  local cap="$caption"
  [[ -n "$open_link" && "$open_link" == https://* ]] && cap="${caption}

🔗 Open it directly: ${open_link}"
  if [[ -n "$local_path" && -s "$local_path" ]]; then
    send_confirmed "$n" --media "$local_path" -m "$cap" && return 0
  fi
  if [[ -n "$url" && "$url" != null && "$url" != file://* ]]; then
    send_confirmed "$n" --video "$url" -m "$cap" && return 0
  fi
  local link
  link=$(openable_link "$open_link" "$url")
  if [[ -n "$link" ]]; then
    send_confirmed "$n" -m "${caption}

🔗 ${link}" && return 0
  fi
  return 1
}

failed_messages=()

# ---- Message 1: Announcement ----
if is_delivered 1; then
  log "INFO" "msg 1: already delivered (has messageId) -- skipping"
else
  log "INFO" "msg 1: sending announcement"
  MSG1="🎉 ${OWNER_NAME}, your zero-human company is built.

Over the past few hours your AI workforce has been getting itself set up.
${N_DEPTS} departments. ${N_ROLES} AI employees. All hired, briefed, and ready to work for you.

Here's what I want to show you:"
  if send_text 1 "$MSG1"; then
    log "INFO" "msg 1: delivered"
    sleep 10
  else
    record_failed 1 "no-messageId-after-3-attempts"
    log "ERROR" "msg 1: FAILED -- no messageId after 3 attempts -- aborting (no point sending celebration if announcement didn't land)"
    state_set '.closeoutStatus = "failed" | .closeoutFailureReason = "telegram-message-1: no messageId after 3 retries"'
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
  if send_photo 2 "$INFO_1" "📊 Your workforce structure -- how your AI company is organized." "$INFO_1_LOCAL" "$GHL_INF1_PUBLIC_URL"; then
    log "INFO" "msg 2: delivered"
    sleep 5
  else
    record_failed 2 "no-messageId"
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
  if send_photo 3 "$INFO_2" "⚙️ How the work flows -- from a task you give me, all the way to a finished output." "" "$GHL_INF2_PUBLIC_URL"; then
    log "INFO" "msg 3: delivered"
    sleep 5
  else
    record_failed 3 "no-messageId"
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
  if send_text 4 "$MSG4_DEFERRED"; then
    log "INFO" "msg 4: deferred-notice delivered"
    sleep 4
  else
    record_failed 4 "no-messageId"
    log "ERROR" "msg 4: FAILED -- continuing"
    failed_messages+=("msg-4")
  fi
elif [[ ( -z "$VIDEO" || "$VIDEO" == "null" ) && ( -z "$VIDEO_LOCAL" || ! -s "$VIDEO_LOCAL" ) && ( -z "$GHL_VIDEO_PUBLIC_URL" || "$GHL_VIDEO_PUBLIC_URL" != https://* ) ]]; then
  log "WARN" "msg 4: celebrationVideoUrl, celebrationVideoLocalPath, and ghlVideoPublicUrl all missing -- skipping"
  failed_messages+=("msg-4-no-url")
else
  log "INFO" "msg 4: sending celebration video"
  if send_video 4 "$VIDEO" "🎬 A quick celebration -- congratulations on launching ${COMPANY_NAME}'s zero-human workforce." "$VIDEO_LOCAL" "$GHL_VIDEO_PUBLIC_URL"; then
    log "INFO" "msg 4: delivered"
    sleep 8
  else
    record_failed 4 "no-messageId"
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
  if send_text 5 "$MSG5"; then
    log "INFO" "msg 5: delivered"
    sleep 3
  else
    record_failed 5 "no-messageId"
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
  # v10.x: append the Convert and Flow media links if the closeout media was
  # uploaded to the client's GHL location. We post the DURABLE, openable PUBLIC
  # per-file links (storage.googleapis.com/msgsndr/... -- no login needed) so the
  # client can open the exact video/graphic any time, then the media-library app
  # link as a "browse them all in your account" convenience.
  GHL_MEDIA_LINE=""
  GHL_PUBLIC_LINES=""
  [[ -n "$GHL_VIDEO_PUBLIC_URL" && "$GHL_VIDEO_PUBLIC_URL" == https://* ]] && GHL_PUBLIC_LINES="${GHL_PUBLIC_LINES}
- 🎬 Celebration video: ${GHL_VIDEO_PUBLIC_URL}"
  [[ -n "$GHL_INF1_PUBLIC_URL" && "$GHL_INF1_PUBLIC_URL" == https://* ]] && GHL_PUBLIC_LINES="${GHL_PUBLIC_LINES}
- 📊 Workforce structure: ${GHL_INF1_PUBLIC_URL}"
  [[ -n "$GHL_INF2_PUBLIC_URL" && "$GHL_INF2_PUBLIC_URL" == https://* ]] && GHL_PUBLIC_LINES="${GHL_PUBLIC_LINES}
- ⚙️ How work flows: ${GHL_INF2_PUBLIC_URL}"
  if [[ -n "$GHL_PUBLIC_LINES" ]]; then
    GHL_MEDIA_LINE="

📁 Your celebration media is also saved in your Convert and Flow media library -- open any of these directly:${GHL_PUBLIC_LINES}"
    if [[ -n "$GHL_MEDIA_URL" && "$GHL_MEDIA_URL" == https://* ]]; then
      GHL_MEDIA_LINE="${GHL_MEDIA_LINE}

(Browse them all in your account: ${GHL_MEDIA_URL})"
    fi
  elif [[ -n "$GHL_MEDIA_URL" && "$GHL_MEDIA_URL" == https://* ]]; then
    GHL_MEDIA_LINE="

📁 Your celebration video and graphics are also in your Convert and Flow media library:
${GHL_MEDIA_URL}"
  fi
  MSG6="🎛️ Your BlackCEO Command Center:
${CC_URL}

This is where you'll talk to your CEO (${AGENT_NAME}), watch tasks move across the Kanban board, and check in on every department. Open it in your browser and bookmark it.${GHL_MEDIA_LINE}

When you're ready, just message me with the first thing you want done. I'm standing by.

-- ${AGENT_NAME}"
  if send_text 6 "$MSG6"; then
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
    record_failed 6 "no-messageId"
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
  if send_text 7 "$MSG7"; then
    log "INFO" "msg 7: delivered"
  else
    record_failed 7 "no-messageId"
    log "ERROR" "msg 7: FAILED -- continuing"
    failed_messages+=("msg-7")
  fi
fi

# ---- summary ----
if (( ${#failed_messages[@]} == 0 )); then
  state_set '.closeoutStatus = "sent"'
  log "INFO" "all messages delivered (each has a captured messageId) -- closeoutStatus=sent"
  exit 0
else
  reason="telegram-partial: $(IFS=,; echo "${failed_messages[*]}")"
  state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\""
  log "ERROR" "delivery partial; failed: ${failed_messages[*]}"
  exit 1
fi
