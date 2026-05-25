#!/usr/bin/env bash
# resume-workforce-build.sh — autonomous resume layer for Skill 23 builds
#
# Reads /data/.openclaw/workspace/.workforce-build-state.json. If the state
# shows pending or stale-building departments, sends a self-message via
# `openclaw message send` from the operator's chat (owner OR operator) to the
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
RUN_COUNT_FILE="$OC_ROOT/workspace/.workforce-build-resume-runs.count"
MAX_ATTEMPTS_DEFAULT=12
STALE_BUILDING_MINUTES=15
# v10.14.36 — defense-in-depth max-runs cap.
# After 24 fires (6h at 15-min intervals) the cron auto-removes itself
# regardless of state. A workforce build that hasn't completed in 6 hours
# is stuck; the cron is no longer useful, kill it.
MAX_RUNS_BEFORE_SELF_REMOVE=24

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"
}

# Remote Rescue v1 — resolve the operator's Telegram chat ID for escalations.
# Lookup order: env.vars.OPERATOR_TELEGRAM_CHAT_ID -> $OPERATOR_TELEGRAM_CHAT_ID
# -> $OPENCLAW_TREVOR_CHAT (legacy) -> hardcoded 5252140759 (Trevor default).
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in
      ""|*"not found"*|*"Error"*) v="" ;;
    esac
  fi
  if [[ -z "$v" && -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]]; then
    v="$OPERATOR_TELEGRAM_CHAT_ID"
  fi
  if [[ -z "$v" && -n "${OPENCLAW_TREVOR_CHAT:-}" ]]; then
    v="$OPENCLAW_TREVOR_CHAT"
  fi
  if [[ -z "$v" ]]; then
    v="5252140759"
  fi
  printf '%s' "$v"
}

# v10.14.36 — locate this cron's UUID by name so we can self-remove.
# OpenClaw doesn't pass a CRON_UUID env var, so we resolve by --name.
# Returns empty string if openclaw CLI is unavailable or the cron isn't listed.
find_self_cron_uuid() {
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/workforce-build-resume/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}

# v10.14.36 — self-remove the workforce-build-resume cron. Tolerates missing
# UUID/CLI; logs whatever it can. Never errors out the script.
self_remove_cron() {
  local reason="$1"
  local uuid
  uuid=$(find_self_cron_uuid)
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not resolve workforce-build-resume UUID — leaving cron in place"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if openclaw cron rm "$uuid" 2>>"$LOG_FILE"; then
    log "self_remove_cron($reason): removed $uuid"
    rm -f "$RUN_COUNT_FILE" 2>/dev/null || true
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED — see errors above"
  fi
}

# ---- v10.14.36: BELT — explicit self-stop on terminal state ----
if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  _build_status=$(jq -r '.status // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _closeout_status=$(jq -r '.closeoutStatus // ""' "$STATE_FILE" 2>/dev/null || echo "")
  _build_completed_at=$(jq -r '.buildCompletedAt // ""' "$STATE_FILE" 2>/dev/null || echo "")
  case "$_build_status" in
    done|failed|complete)
      _terminal=1 ;;
    *)
      _terminal=0 ;;
  esac
  if (( _terminal == 0 )) && [[ -n "$_build_completed_at" ]]; then
    case "$_closeout_status" in
      done|sent) _terminal=1 ;;
    esac
  fi
  if (( _terminal == 1 )); then
    log "BELT: terminal state detected (build_status=$_build_status, closeout=$_closeout_status, completed=$_build_completed_at) — removing self-cron and exiting"
    self_remove_cron "terminal-state"
    exit 0
  fi
fi

# ---- v10.14.36: SUSPENDERS — max-runs auto-expire ----
mkdir -p "$(dirname "$RUN_COUNT_FILE")" 2>/dev/null || true
_run_count=0
if [[ -f "$RUN_COUNT_FILE" ]]; then
  _run_count=$(cat "$RUN_COUNT_FILE" 2>/dev/null | tr -dc '0-9' | head -c 6)
  [[ -z "$_run_count" ]] && _run_count=0
fi
_run_count=$((_run_count + 1))
echo "$_run_count" > "$RUN_COUNT_FILE" 2>/dev/null || true
if (( _run_count > MAX_RUNS_BEFORE_SELF_REMOVE )); then
  log "SUSPENDERS: run #$_run_count exceeds cap of $MAX_RUNS_BEFORE_SELF_REMOVE — auto-removing self-cron"
  if command -v openclaw >/dev/null 2>&1; then
    _operator_chat="$(resolve_operator_chat_id)"
    if [[ -n "$_operator_chat" ]]; then
      openclaw message send --channel telegram -t "$_operator_chat" \
        -m "⚠️ workforce-build-resume cron auto-removed after $_run_count runs (>6h). State file: $STATE_FILE on $(hostname). Build is stuck — manual intervention required." 2>>"$LOG_FILE" || true
    fi
  fi
  self_remove_cron "max-runs-exceeded"
  exit 0
fi

# ---- v10.14.20: heal config before any gateway interaction ----
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
  # Final escalation to operator (env.vars.OPERATOR_TELEGRAM_CHAT_ID, default 5252140759).
  _operator_chat="$(resolve_operator_chat_id)"
  if [[ -n "$_operator_chat" ]]; then
    openclaw message send --channel telegram -t "$_operator_chat" \
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

# Find a chat the bot CAN reply to. Priority: owner (already paired) > operator (Remote Rescue).
TARGET_CHAT=""
if [[ -n "$owner_chat" && "$owner_chat" != "null" ]]; then
  TARGET_CHAT="$owner_chat"
else
  TARGET_CHAT="$(resolve_operator_chat_id)"
fi

if [[ -z "$TARGET_CHAT" ]]; then
  log "no usable target chat (ownerChat or operator) — cannot dispatch resume"
  exit 0
fi

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
