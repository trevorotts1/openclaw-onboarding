#!/usr/bin/env bash
# resume-workforce-build.sh — autonomous resume layer for Skill 23 builds
#
# Reads /data/.openclaw/workspace/.workforce-build-state.json. If the state
# shows pending or stale-building departments, sends a self-message via
# `openclaw message send` from the operator's chat (owner OR Trevor) to the
# bot's own chat so the agent gets invoked and continues the build.
#
# This is the ONLY autonomous-recovery layer in the workforce-build pipeline.
# If this script doesn't run on a cron, an interrupted build will sit forever.
#
# Idempotent. Safe to run every N minutes. Holds a 10-minute lockfile so it
# never double-fires while a build is actively running.

set -u

# ---- platform detection (vps default; mac override) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[resume-workforce-build] no OpenClaw root found; aborting" >&2
  exit 0
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOCK_FILE="$OC_ROOT/workspace/.workforce-build-state.lock"
LOG_FILE="$OC_ROOT/workspace/.workforce-build-state.log"
MAX_ATTEMPTS_DEFAULT=12
STALE_BUILDING_MINUTES=15

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"
}

# ---- v10.13.19: heal config before any gateway interaction ----
# The Telegram/whatsapp plugin auto-config-append can write deprecated field
# names (e.g. messages.groupChat.unmentionedInbound) on container restart that
# crash the gateway on next boot. `openclaw doctor --fix` strips them. If the
# gateway is wedged for this reason, our `openclaw message send` below would
# fail silently and the cron's resume-dispatch would never reach the agent.
# Idempotent — safe to run every cron tick.
if command -v openclaw >/dev/null 2>&1; then
  openclaw doctor --fix >/dev/null 2>&1 || true
fi

# ---- preconditions ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE — nothing to resume; exiting clean"
  exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
  log "jq not installed — cannot parse state; exiting"
  exit 0
fi

if ! command -v openclaw >/dev/null 2>&1; then
  log "openclaw CLI not on PATH — cannot dispatch resume; exiting"
  exit 0
fi

# ---- lock (prevent concurrent self-pings) ----
if [[ -f "$LOCK_FILE" ]]; then
  lock_mtime=$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)
  now=$(date +%s)
  lock_age=$(( now - lock_mtime ))
  if (( lock_age < 600 )); then
    log "lock held for ${lock_age}s (< 600s) — another resume in flight; exiting"
    exit 0
  fi
  log "stale lock (age ${lock_age}s) — clearing"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ---- read state ----
interview_complete=$(jq -r '.interviewComplete // false' "$STATE_FILE")
if [[ "$interview_complete" != "true" ]]; then
  log "interview not yet complete — nothing to resume"
  exit 0
fi

pending_count=$(jq -r '[.departments[] | select(.status == "pending" or .status == "failed")] | length' "$STATE_FILE")
stale_building_count=$(jq --arg min "$STALE_BUILDING_MINUTES" -r '
  [.departments[]
    | select(.status == "building")
    | select(.lastAttemptAt != null)
    | select(((now - (.lastAttemptAt | fromdateiso8601)) / 60) > ($min | tonumber))
  ] | length
' "$STATE_FILE" 2>/dev/null || echo 0)

# v10.14.17 — also fire when build is done but closeout is dirty.
# closeoutStatus terminal states: "done", "sent". Anything else (or missing,
# when buildCompletedAt is set) means closeout work is owed.
build_completed_at=$(jq -r '.buildCompletedAt // empty' "$STATE_FILE")
closeout_status=$(jq -r '.closeoutStatus // empty' "$STATE_FILE")
closeout_dirty=0
if [[ -n "$build_completed_at" ]]; then
  case "$closeout_status" in
    done|sent) closeout_dirty=0 ;;
    *) closeout_dirty=1 ;;
  esac
fi

total_attention=$(( pending_count + stale_building_count + closeout_dirty ))
if (( total_attention == 0 )); then
  done_count=$(jq -r '[.departments[] | select(.status == "done")] | length' "$STATE_FILE")
  total_count=$(jq -r '.departments | length' "$STATE_FILE")
  if (( done_count == total_count )) && (( total_count > 0 )); then
    log "ALL ${total_count} departments done + closeout terminal (status=$closeout_status) — nothing to do"
  else
    log "no pending/stale departments and closeout clean (pending=$pending_count, stale=$stale_building_count, closeout=$closeout_status) — nothing to do"
  fi
  exit 0
fi

# ---- attempt cap ----
attempts=$(jq -r '.resumeAttempts // 0' "$STATE_FILE")
max_attempts=$(jq -r ".maxResumeAttempts // $MAX_ATTEMPTS_DEFAULT" "$STATE_FILE")
if (( attempts >= max_attempts )); then
  log "resumeAttempts ($attempts) >= maxResumeAttempts ($max_attempts) — bailing out, no more self-pings"
  # Optional: ping Trevor's chat 5252140759 with a final escalation
  if [[ -n "${OPENCLAW_TREVOR_CHAT:-}" ]]; then
    openclaw message send --channel telegram -t "$OPENCLAW_TREVOR_CHAT" \
      -m "🚨 Workforce build stuck: ${pending_count} pending, ${stale_building_count} stale, ${attempts} resume attempts exhausted. State: $STATE_FILE" 2>>"$LOG_FILE" || true
  fi
  exit 0
fi

# ---- bump attempt counter atomically ----
tmp_state=$(mktemp)
jq ".resumeAttempts = $((attempts + 1))" "$STATE_FILE" > "$tmp_state" && mv "$tmp_state" "$STATE_FILE"

# ---- compose the resume message + dispatch ----
agent_name=$(jq -r '.agentName // "the master orchestrator"' "$STATE_FILE")
owner_chat=$(jq -r '.ownerChat // empty' "$STATE_FILE")
pending_list=$(jq -r '[.departments[] | select(.status == "pending" or .status == "failed") | .slug] | join(", ")' "$STATE_FILE")
stale_list=$(jq -r --arg min "$STALE_BUILDING_MINUTES" '
  [.departments[]
    | select(.status == "building")
    | select(.lastAttemptAt != null)
    | select(((now - (.lastAttemptAt | fromdateiso8601)) / 60) > ($min | tonumber))
    | .slug] | join(", ")
' "$STATE_FILE")

# Find a chat the bot CAN reply to. Priority: owner (already paired) > Trevor (operator).
# A bot can only send to chats that have messaged it first. Operator chat is usually paired during onboarding.
TARGET_CHAT=""
if [[ -n "$owner_chat" && "$owner_chat" != "null" ]]; then
  TARGET_CHAT="$owner_chat"
elif [[ -n "${OPENCLAW_TREVOR_CHAT:-}" ]]; then
  TARGET_CHAT="$OPENCLAW_TREVOR_CHAT"
fi

if [[ -z "$TARGET_CHAT" ]]; then
  log "no usable target chat (ownerChat or OPENCLAW_TREVOR_CHAT) — cannot dispatch resume"
  exit 0
fi

# IMPORTANT: this is a SELF-PING. The bot sends a system-tagged message to a paired chat.
# The agent reads it as an internal trigger. We tag with [WORKFORCE-RESUME] so the
# Skill 23 INSTRUCTIONS.md "Post-Interview Handoff Protocol" knows to treat it as
# a build-resume invocation (NOT a new interview question and NOT a user message).
#
# v10.14.17: tag also drives closeout pickup. When pending/stale are empty but
# closeout_dirty=1, the agent reads closeoutStatus and skips ahead to Skill 37.
if (( closeout_dirty == 1 )) && (( pending_count == 0 )) && (( stale_building_count == 0 )); then
  msg="[CLOSEOUT-RESUME] ${agent_name}: workforce build is done (buildCompletedAt set) but closeout is incomplete (closeoutStatus=${closeout_status:-unset}). Read /data/.openclaw/skills/37-zhc-closeout/INSTRUCTIONS.md and invoke scripts/run-closeout.sh. The script is idempotent — it picks up from the first un-completed step. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this — the owner only hears from you when Skill 37 Step 6 fires."
else
  msg="[WORKFORCE-RESUME] ${agent_name}: continue the workforce build per the Post-Interview Handoff Protocol in Skill 23. Read .workforce-build-state.json. Pending: ${pending_list:-none}. Stale: ${stale_list:-none}. Closeout status: ${closeout_status:-unset}. Resume attempt $((attempts + 1)) of $max_attempts. Do NOT message the owner about this — the resume is internal. When all departments are done, set closeoutStatus=pending and either invoke ~/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh inline OR exit and let the next cron fire pick up the closeout."
fi

log "dispatching resume to chat $TARGET_CHAT (attempt $((attempts + 1))/$max_attempts; pending='$pending_list'; stale='$stale_list'; closeout_dirty=$closeout_dirty closeout_status='$closeout_status')"
if openclaw message send --channel telegram -t "$TARGET_CHAT" -m "$msg" 2>>"$LOG_FILE"; then
  log "resume dispatch ok"
else
  log "resume dispatch FAILED — see errors above"
fi

exit 0
