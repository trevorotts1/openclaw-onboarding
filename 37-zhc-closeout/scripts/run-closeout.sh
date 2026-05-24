#!/usr/bin/env bash
# run-closeout.sh — top-level orchestrator for Skill 37 ZHC Closeout.
#
# Reads .workforce-build-state.json and walks through the 6-step pipeline:
#   1. Skill 32 (Command Center)
#   2. Infographic #1 (Workforce Structure)
#   3. Infographic #2 (How Work Flows)
#   4. Celebration video (Veo 3.1)
#   5. Notion page tree (9 sections)
#   6. Telegram delivery (6 paced messages)
#
# Idempotent — each step skips if its target URL field is already set.
# All steps write state atomically. The resume cron can pick up a stalled
# closeout at any point and continue from the first un-completed step.

set -u

# ---- platform detection (VPS first, Mac fallback) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[run-closeout] no OpenClaw root found; aborting" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

state_get() {
  jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null
}

state_set() {
  # Usage: state_set '.field = value | .other = value'
  local tmp
  tmp=$(mktemp)
  if jq "$1" "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "state_set failed for expr: $1"
    return 1
  fi
}

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

fail_closeout() {
  local reason="$1"
  log "ERROR" "marking closeout failed: $reason"
  state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"$reason\""
  exit 1
}

# ---- preflight ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "ERROR" "no state file at $STATE_FILE — nothing to close out"
  exit 1
fi
for cmd in jq curl openclaw; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "ERROR" "preflight: missing required command: $cmd"
    state_set ".closeoutStatus = \"failed\" | .closeoutFailureReason = \"preflight: missing $cmd\""
    exit 1
  fi
done
if [[ -z "${KIE_API_KEY:-}" ]]; then
  fail_closeout "preflight: KIE_API_KEY env var not set"
fi
if [[ -z "${NOTION_API_TOKEN:-}" ]]; then
  fail_closeout "preflight: NOTION_API_TOKEN env var not set"
fi

build_completed_at=$(state_get '.buildCompletedAt')
if [[ -z "$build_completed_at" || "$build_completed_at" == "null" ]]; then
  log "INFO" "buildCompletedAt not set yet — Skill 23 not done; nothing to do"
  exit 0
fi

closeout_status=$(state_get '.closeoutStatus')
if [[ "$closeout_status" == "done" || "$closeout_status" == "sent" ]]; then
  log "INFO" "closeoutStatus=$closeout_status — already complete; nothing to do"
  exit 0
fi

# ---- transition pending → generating (idempotent) ----
if [[ "$closeout_status" != "generating" ]]; then
  state_set ".closeoutStatus = \"generating\" | .closeoutStartedAt = \"$(now_iso)\""
  log "INFO" "closeout started — closeoutStatus transitioned to generating"
fi

# ----------------------------------------------------------------------
# STEP 1 — Skill 32 (Command Center) — v10.14.19: REAL materialize + verify
# ----------------------------------------------------------------------
# For weeks before v10.14.19, this step would silently mark commandCenterStatus
# = "done" with a fake http://localhost:4000 URL whenever Skill 32's
# setup-command-center.sh was missing — which it ALWAYS was, because that
# script never existed. The new contract:
#   1. Run Skill 32's materialize-dept-agents.sh (registers each workspace
#      dept folder as a real entry in openclaw.json's agents.list[])
#   2. Verify agents.list[].length >= 2 (default "main" + at least 1 dept)
#   3. ONLY THEN mark commandCenterStatus = "done"
#   4. commandCenterUrl is set only if a Mission Control dashboard is
#      actually reachable on :4000; otherwise leave null.
# No more lying.
log "INFO" "step=1 command-center: starting"
cc_status=$(state_get '.commandCenterStatus')
if [[ "$cc_status" == "done" ]]; then
  log "INFO" "step=1 command-center: already done — skipping"
else
  state_set '.commandCenterStatus = "building"'

  SKILL32_MATERIALIZE="$OC_ROOT/skills/32-command-center-setup/scripts/materialize-dept-agents.sh"
  if [[ ! -x "$SKILL32_MATERIALIZE" ]]; then
    log "ERROR" "step=1 command-center: materialize-dept-agents.sh not executable or missing at $SKILL32_MATERIALIZE — refusing to mark done"
    state_set '.commandCenterStatus = "failed"'
    fail_closeout "Skill 32 materialize script not installed"
  fi

  log "INFO" "step=1 command-center: running materialize-dept-agents.sh"
  if ! bash "$SKILL32_MATERIALIZE" >> "$LOG_FILE" 2>&1; then
    log "ERROR" "step=1 command-center: materialize-dept-agents.sh failed (see log)"
    state_set '.commandCenterStatus = "failed"'
    fail_closeout "Skill 32 materialize-dept-agents.sh exited non-zero"
  fi

  # Verify agents.list[] actually got populated (default main + >=1 dept)
  AGENT_COUNT=$(python3 -c "import json,sys; sys.stdout.write(str(len(json.load(open('$OC_ROOT/openclaw.json'))['agents']['list'])))" 2>>"$LOG_FILE" || echo "0")
  if [[ -z "$AGENT_COUNT" || "$AGENT_COUNT" -lt 2 ]]; then
    log "ERROR" "step=1 command-center: agents.list has only ${AGENT_COUNT:-0} entries after materialize — failing closeout"
    state_set ".commandCenterStatus = \"failed\""
    fail_closeout "agents.list[] not populated after Skill 32 materialize (count=${AGENT_COUNT:-0})"
  fi
  log "INFO" "step=1 command-center: ${AGENT_COUNT} agents materialized in agents.list[]"

  # Also push the agentsMaterializedCount into state for downstream visibility
  state_set ".agentsMaterializedCount = $AGENT_COUNT"

  # Command Center dashboard URL — set ONLY if real, never fake
  if curl -sf --max-time 3 http://127.0.0.1:4000/ >/dev/null 2>&1; then
    state_set '.commandCenterStatus = "done" | .commandCenterUrl = "http://127.0.0.1:4000/"'
    log "INFO" "step=1 command-center: done — Mission Control dashboard reachable at http://127.0.0.1:4000/"
  else
    state_set '.commandCenterStatus = "done" | .commandCenterUrl = null'
    log "WARN" "step=1 command-center: Mission Control dashboard at :4000 not running — leaving commandCenterUrl null"
  fi
fi

# ----------------------------------------------------------------------
# STEP 2 — Infographic #1 (Workforce Structure)
# ----------------------------------------------------------------------
log "INFO" "step=2 infographic-1: starting"
if [[ -n "$(state_get '.infographic1Url')" && "$(state_get '.infographic1Url')" != "null" ]]; then
  log "INFO" "step=2 infographic-1: already done — skipping"
else
  if ! bash "$SKILL_DIR/scripts/generate-infographics.sh" structure; then
    fail_closeout "infographic-1: generation failed (see log)"
  fi
fi

# ----------------------------------------------------------------------
# STEP 3 — Infographic #2 (How Work Flows)
# ----------------------------------------------------------------------
log "INFO" "step=3 infographic-2: starting"
if [[ -n "$(state_get '.infographic2Url')" && "$(state_get '.infographic2Url')" != "null" ]]; then
  log "INFO" "step=3 infographic-2: already done — skipping"
else
  if ! bash "$SKILL_DIR/scripts/generate-infographics.sh" workflow; then
    fail_closeout "infographic-2: generation failed (see log)"
  fi
fi

# ----------------------------------------------------------------------
# STEP 4 — Celebration Video (Veo 3.1)
# ----------------------------------------------------------------------
log "INFO" "step=4 celebration-video: starting"
if [[ -n "$(state_get '.celebrationVideoUrl')" && "$(state_get '.celebrationVideoUrl')" != "null" ]]; then
  log "INFO" "step=4 celebration-video: already done — skipping"
else
  if ! bash "$SKILL_DIR/scripts/generate-celebration-video.sh"; then
    fail_closeout "celebration-video: generation failed (see log)"
  fi
fi

# ----------------------------------------------------------------------
# STEP 5 — Notion Page Tree
# ----------------------------------------------------------------------
log "INFO" "step=5 notion: starting"
if [[ -n "$(state_get '.notionRootPageUrl')" && "$(state_get '.notionRootPageUrl')" != "null" ]]; then
  log "INFO" "step=5 notion: already done — skipping"
else
  if ! bash "$SKILL_DIR/scripts/create-notion-closeout.sh"; then
    fail_closeout "notion: page-tree creation failed (see log)"
  fi
fi

# ----------------------------------------------------------------------
# STEP 6 — Telegram Delivery
# ----------------------------------------------------------------------
log "INFO" "step=6 telegram: starting 6-message delivery sequence"
if ! bash "$SKILL_DIR/scripts/send-telegram-celebration.sh"; then
  # send-telegram-celebration.sh handles its own retry + failure marking.
  # If we get here with a non-zero exit, partial delivery may have happened.
  log "ERROR" "step=6 telegram: delivery script returned non-zero"
  # Don't fail_closeout here — partial delivery is tracked in messagesDelivered[]
  # and the resume cron will retry the missing messages.
  exit 1
fi

# ----------------------------------------------------------------------
# Finalize
# ----------------------------------------------------------------------
state_set ".closeoutStatus = \"done\" | .closeoutCompletedAt = \"$(now_iso)\""
log "INFO" "closeout complete — closeoutStatus=done"
exit 0
