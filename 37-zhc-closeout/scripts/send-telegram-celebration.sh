#!/usr/bin/env bash
# send-telegram-celebration.sh — 6-message paced Telegram delivery to the owner.
#
# Tracks per-message delivery in state.messagesDelivered = [1,2,3,4,5,6].
# Each message is idempotent — re-running only sends messages not yet in the
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
INFO_2=$(state_get '.infographic2Url')
VIDEO=$(state_get '.celebrationVideoUrl')
NOTION_URL=$(state_get '.notionRootPageUrl')
CC_URL=$(state_get '.commandCenterUrl')

if [[ -z "$OWNER_CHAT" || "$OWNER_CHAT" == "null" ]]; then
  log "ERROR" "ownerChat missing from state — cannot deliver"
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

# Send a photo with caption via openclaw if it supports --photo, else fall back
# to a text message that includes the URL. Returns 0 on success.
send_photo() {
  local url="$1"
  local caption="$2"
  local attempt=0
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    # Try openclaw photo flag first (best). If unsupported, fall back to text+URL.
    if openclaw message send --channel telegram -t "$OWNER_CHAT" --photo "$url" -m "$caption" >> "$LOG_FILE" 2>&1; then
      return 0
    fi
    # Fallback: send caption + URL as plain text
    if openclaw message send --channel telegram -t "$OWNER_CHAT" -m "${caption}

${url}" >> "$LOG_FILE" 2>&1; then
      return 0
    fi
    log "WARN" "send_photo attempt $attempt failed"
    sleep $((2 ** attempt))
  done
  return 1
}

send_video() {
  local url="$1"
  local caption="$2"
  local attempt=0
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    if openclaw message send --channel telegram -t "$OWNER_CHAT" --video "$url" -m "$caption" >> "$LOG_FILE" 2>&1; then
      return 0
    fi
    if openclaw message send --channel telegram -t "$OWNER_CHAT" -m "${caption}

${url}" >> "$LOG_FILE" 2>&1; then
      return 0
    fi
    log "WARN" "send_video attempt $attempt failed"
    sleep $((2 ** attempt))
  done
  return 1
}

failed_messages=()

# ---- Message 1: Announcement ----
if is_delivered 1; then
  log "INFO" "msg 1: already delivered — skipping"
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
    log "ERROR" "msg 1: FAILED after 3 attempts — aborting (no point sending celebration if announcement didn't land)"
    state_set '.closeoutStatus = "failed" | .closeoutFailureReason = "telegram-message-1: 3 retries exhausted"'
    exit 1
  fi
fi

# ---- Message 2: Infographic #1 ----
if is_delivered 2; then
  log "INFO" "msg 2: already delivered — skipping"
elif [[ -z "$INFO_1" || "$INFO_1" == "null" ]]; then
  log "WARN" "msg 2: infographic1Url missing — skipping"
  failed_messages+=("msg-2-no-url")
else
  log "INFO" "msg 2: sending infographic #1"
  if send_photo "$INFO_1" "📊 Your workforce structure — how your AI company is organized."; then
    mark_delivered 2
    log "INFO" "msg 2: delivered"
    sleep 5
  else
    log "ERROR" "msg 2: FAILED — continuing"
    failed_messages+=("msg-2")
  fi
fi

# ---- Message 3: Infographic #2 ----
if is_delivered 3; then
  log "INFO" "msg 3: already delivered — skipping"
elif [[ -z "$INFO_2" || "$INFO_2" == "null" ]]; then
  log "WARN" "msg 3: infographic2Url missing — skipping"
  failed_messages+=("msg-3-no-url")
else
  log "INFO" "msg 3: sending infographic #2"
  if send_photo "$INFO_2" "⚙️ How the work flows — from a task you give me, all the way to a finished output."; then
    mark_delivered 3
    log "INFO" "msg 3: delivered"
    sleep 5
  else
    log "ERROR" "msg 3: FAILED — continuing"
    failed_messages+=("msg-3")
  fi
fi

# ---- Message 4: Celebration video ----
if is_delivered 4; then
  log "INFO" "msg 4: already delivered — skipping"
elif [[ -z "$VIDEO" || "$VIDEO" == "null" ]]; then
  log "WARN" "msg 4: celebrationVideoUrl missing — skipping"
  failed_messages+=("msg-4-no-url")
else
  log "INFO" "msg 4: sending celebration video"
  if send_video "$VIDEO" "🎬 A quick celebration — congratulations on launching ${COMPANY_NAME}'s zero-human workforce."; then
    mark_delivered 4
    log "INFO" "msg 4: delivered"
    sleep 8
  else
    log "ERROR" "msg 4: FAILED — continuing"
    failed_messages+=("msg-4")
  fi
fi

# ---- Message 5: Notion doc link ----
if is_delivered 5; then
  log "INFO" "msg 5: already delivered — skipping"
elif [[ -z "$NOTION_URL" || "$NOTION_URL" == "null" ]]; then
  log "WARN" "msg 5: notionRootPageUrl missing — skipping"
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
    log "ERROR" "msg 5: FAILED — continuing"
    failed_messages+=("msg-5")
  fi
fi

# ---- Message 6: Command Center URL ----
if is_delivered 6; then
  log "INFO" "msg 6: already delivered — skipping"
elif [[ -z "$CC_URL" || "$CC_URL" == "null" ]]; then
  log "WARN" "msg 6: commandCenterUrl missing — skipping"
  failed_messages+=("msg-6-no-url")
else
  log "INFO" "msg 6: sending Command Center URL"
  MSG6="🎛️ Your BlackCEO Command Center:
${CC_URL}

This is where you'll talk to your CEO (${AGENT_NAME}), watch tasks move across the Kanban board, and check in on every department. Open it in your browser and bookmark it.

When you're ready, just message me with the first thing you want done. I'm standing by."
  if send_text "$MSG6"; then
    mark_delivered 6
    log "INFO" "msg 6: delivered"
  else
    log "ERROR" "msg 6: FAILED — continuing"
    failed_messages+=("msg-6")
  fi
fi

# ---- summary ----
if (( ${#failed_messages[@]} == 0 )); then
  state_set '.closeoutStatus = "sent"'
  log "INFO" "all 6 messages delivered — closeoutStatus=sent"
  exit 0
else
  reason="telegram-partial: $(IFS=,; echo "${failed_messages[*]}")"
  state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\""
  log "ERROR" "delivery partial; failed: ${failed_messages[*]}"
  exit 1
fi
