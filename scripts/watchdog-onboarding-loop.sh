#!/usr/bin/env bash
# ============================================================
# scripts/watchdog-onboarding-loop.sh — PRD 2.13 Watchdog Loop
# v3 (nudge-lifecycle): dormant/credit-backoff awareness added on top of
#     v2 (furnace-fix): interview gate + wave-backoff + shared dispatch lock
# ============================================================
# PURPOSE:
#   Loop-engineers the install so it keeps itself going with no stalls
#   between waves. Fires every 10-15 min (registered by install.sh).
#
# LOOP DOCTRINE (PRD 2.13):
#   1. CHEAP STATE-FILE CHECK FIRST (near-zero tokens). Only when a
#      per-wave or overall goal is found incomplete does the watchdog
#      re-prompt the agent — and ONLY with the EXACT next incomplete
#      wave (never a vague "continue onboarding").
#   2. TELEGRAM PROGRESS PINGS per wave transition.
#   3. 3-STRIKE ESCALATION: a wave failing its goal check 3 consecutive
#      cycles stops the loop and alerts the operator with the failing check.
#   4. SELF-KILL: unregisters its own cron the moment the overall goal
#      verifies. Closeout QC asserts zero onboarding loops left running.
#   5. LOOP REGISTRY: every fired instance verifies its cron UUID is
#      in the loop registry; self-register if missing (idempotent).
#
# NEVER-STOP / KILL CONDITION:
#   This watchdog ONLY stops when oc_overall_goal_check returns 0.
#   It does NOT stop on: a self-declared "done" from the agent, a
#   missing state file (just logs and exits clean), or a timeout.
#   3-strike escalation stops the LOOP but alerts the operator —
#   it is the operator's explicit "ack + fix" that can restart.
#
# EXIT CODES:
#   0  — clean exit (overall goal passed → self-killed, or no state file yet)
#   0  — also on 3-strike stop (halted + escalated; operator must restart)
#   1  — lock timeout (another watchdog instance running within 10 min)
#
# LOOP REGISTRY: registers itself as "watchdog-onboarding-loop".
# ============================================================

set -u

# ── platform + path resolution ────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "${HOME:-/root}/.openclaw" ]]; then
  OC_ROOT="${HOME:-/root}/.openclaw"
else
  echo "[watchdog-onboarding-loop] no OpenClaw root found; exiting clean" >&2
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
REPO_ROOT=""
[[ -n "$SCRIPT_DIR" ]] && REPO_ROOT="$(cd "$SCRIPT_DIR/.." 2>/dev/null && pwd || echo "")"

# Locate gate library (canonical: lib-onboarding-state.sh at repo root)
GATE_LIB=""
for _cand in \
  "${REPO_ROOT:+$REPO_ROOT/lib-onboarding-state.sh}" \
  "$SCRIPT_DIR/onboarding-state.sh" \
  "$OC_ROOT/scripts/onboarding-state.sh" \
  "$OC_ROOT/onboarding/scripts/onboarding-state.sh" \
  "$HOME/.openclaw/scripts/onboarding-state.sh"; do
  [[ -n "$_cand" && -f "$_cand" ]] && GATE_LIB="$_cand" && break
done

# Locate loop registry lib
LOOP_REG_LIB=""
for _cand in \
  "${SCRIPT_DIR:+$SCRIPT_DIR/loop-registry.sh}" \
  "$OC_ROOT/scripts/loop-registry.sh" \
  "$OC_ROOT/onboarding/scripts/loop-registry.sh"; do
  [[ -n "$_cand" && -f "$_cand" ]] && LOOP_REG_LIB="$_cand" && break
done

WS="$OC_ROOT/workspace"
STATE_FILE="${ONBOARDING_STATE_FILE:-$WS/.onboarding-state.json}"
LOCK_FILE="$WS/.watchdog-onboarding-loop.lock"
LOG_FILE="$WS/.watchdog-onboarding-loop.log"
LOOP_REGISTRY_FILE="$WS/.loop-registry.json"
SHARED_DISPATCH_LOCK="$WS/.onboarding-dispatch.lock"   # shared with resume-onboarding.sh
LOOP_NAME="watchdog-onboarding-loop"
MAX_STRIKES=3   # 3 consecutive check failures on the same wave → escalate + halt

# Nudge lifecycle state file (shared with resume-onboarding.sh — pure file I/O)
NUDGE_STATE_FILE="$WS/.onboarding-nudge-state"
NUDGE_REARM_FILE="$WS/.onboarding-nudge-rearm"

log() { printf '%s [watchdog] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"; }

# ── nudge state read helper (cheap, no model call) ───────────────────────────
nudge_get() {
  local key="$1" val=""
  [[ -f "$NUDGE_STATE_FILE" ]] && val="$(grep "^${key}=" "$NUDGE_STATE_FILE" 2>/dev/null | head -1 | cut -d= -f2-)" || true
  printf '%s' "$val"
}
nudge_set() {
  local key="$1" value="$2"
  mkdir -p "$WS" 2>/dev/null || true
  if [[ -f "$NUDGE_STATE_FILE" ]] && grep -q "^${key}=" "$NUDGE_STATE_FILE" 2>/dev/null; then
    local tmp; tmp="$(mktemp)"
    sed "s|^${key}=.*|${key}=${value}|" "$NUDGE_STATE_FILE" > "$tmp" 2>/dev/null && mv "$tmp" "$NUDGE_STATE_FILE" || rm -f "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >> "$NUDGE_STATE_FILE" 2>/dev/null || true
  fi
}
nudge_credit_fail_dormant() {
  # Enter dormant on credit failure + notify operator ONCE.
  local now; now="$(date +%s)"
  local already; already="$(nudge_get credit_notified)"
  nudge_set dormant true
  nudge_set credit_fail_ts "$now"
  log "NUDGE-LIFECYCLE[watchdog]: credit-failure — entering DORMANT"
  if [[ "$already" != "true" ]]; then
    nudge_set credit_notified true
    local op; op="$(resolve_operator_chat_id)"
    if [[ -n "$op" ]] && command -v openclaw >/dev/null 2>&1; then
      openclaw message send --channel telegram -t "$op" \
        -m "⚠️ [ONBOARDING-WATCHDOG] $(hostname): model call returned 402/429 (payment/quota). Entering DORMANT — will NOT retry autonomously. Onboarding resumes when the owner sends any message. Check billing/quota." \
        2>>"$LOG_FILE" || true
    fi
  fi
}

# ── operator chat resolver ────────────────────────────────────────────────────
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_HELP_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    if [[ -z "$v" ]]; then
      v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
      case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    fi
  fi
  [[ -z "$v" && -n "${OPERATOR_HELP_CHAT_ID:-}" ]] && v="$OPERATOR_HELP_CHAT_ID"
  [[ -z "$v" ]] && v="5252140759"
  printf '%s' "$v"
}

# ── cron self-management ──────────────────────────────────────────────────────
find_self_cron_uuid() {
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  # Try loop registry first (accurate)
  if [[ -n "$LOOP_REG_LIB" ]]; then
    # shellcheck disable=SC1090
    source "$LOOP_REG_LIB" 2>/dev/null || true
    local uuid
    uuid="$(LOOP_REGISTRY_FILE="$LOOP_REGISTRY_FILE" lr_get_uuid "$LOOP_NAME" 2>/dev/null)"
    [[ -n "$uuid" && "$uuid" != "null" ]] && { echo "$uuid"; return 0; }
  fi
  # Fallback: scan openclaw cron list by name
  openclaw cron list 2>/dev/null \
    | awk "/watchdog-onboarding-loop/ { for (i=1;i<=NF;i++) if (\$i ~ /^[0-9a-fA-F-]{8,}\$/) { print \$i; exit } }" \
    | head -1
}

self_remove_cron() {
  local reason="$1"
  local uuid
  uuid="$(find_self_cron_uuid)"
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not resolve watchdog UUID — leaving"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if command -v openclaw >/dev/null 2>&1 && openclaw cron rm "$uuid" 2>>"$LOG_FILE"; then
    log "self_remove_cron($reason): removed $uuid"
    # Mark killed in loop registry
    if [[ -n "$LOOP_REG_LIB" ]]; then
      # shellcheck disable=SC1090
      source "$LOOP_REG_LIB" 2>/dev/null || true
      LOOP_REGISTRY_FILE="$LOOP_REGISTRY_FILE" lr_kill "$LOOP_NAME" 2>/dev/null || true
    fi
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED (or openclaw not found)"
  fi
}

# ── ensure gate library is available ─────────────────────────────────────────
if [[ -z "$GATE_LIB" ]]; then
  log "gate library (lib-onboarding-state.sh) not found — cannot run wave checks; exiting clean"
  exit 0
fi
# shellcheck disable=SC1090
source "$GATE_LIB" 2>/dev/null || { log "failed to source $GATE_LIB"; exit 0; }

# Load loop registry lib if available
if [[ -n "$LOOP_REG_LIB" ]]; then
  # shellcheck disable=SC1090
  source "$LOOP_REG_LIB" 2>/dev/null || true
fi

# ── preconditions ─────────────────────────────────────────────────────────────
mkdir -p "$WS" 2>/dev/null || true

if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE — install not yet started or no skills tracked; exiting clean"
  exit 0
fi

# ── CHEAP OVERALL GOAL CHECK FIRST (near-zero tokens) ─────────────────────────
# This runs before any agent call, before any lock. If we're already done, bail.
# Export OC_CONFIG + ONBOARDING_STATE_FILE so the gate functions find the right files.
export OC_CONFIG="$OC_ROOT"
export ONBOARDING_STATE_FILE="$STATE_FILE"
export OC_WORKSPACE_DEFAULT="$WS"

log "CHEAP-CHECK: running oc_overall_goal_check on $STATE_FILE"
oc_wave_state_init 2>/dev/null || true  # ensure waveGoals block exists

OVERALL_RC=1
oc_overall_goal_check 2>/dev/null && OVERALL_RC=0

if [[ "$OVERALL_RC" -eq 0 ]]; then
  log "OVERALL GOAL PASSED — all waves verified, interview complete, workforce built, closeout delivered"
  log "Self-removing watchdog cron (kill condition met)"
  self_remove_cron "overall-goal-passed"
  exit 0
fi

# ── lock (prevent double-fire) ────────────────────────────────────────────────
if [[ -f "$LOCK_FILE" ]]; then
  _lock_mtime=$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)
  _now_ts=$(date +%s)
  _age=$(( _now_ts - _lock_mtime ))
  if (( _age < 600 )); then
    log "lock held ${_age}s (<600) — another watchdog in flight; exiting"
    exit 1
  fi
  log "stale lock (age ${_age}s) — clearing"
fi
printf '%d\n' "$$" > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ── self-register in loop registry ───────────────────────────────────────────
if command -v lr_register >/dev/null 2>&1; then
  _self_uuid="$(find_self_cron_uuid)"
  LOOP_REGISTRY_FILE="$LOOP_REGISTRY_FILE" lr_register "$LOOP_NAME" \
    "${_self_uuid:-unknown}" "openclaw cron rm ${_self_uuid:-unknown}" 2>/dev/null || true
fi

# ── heal OpenClaw config ──────────────────────────────────────────────────────
openclaw doctor --fix >/dev/null 2>&1 || true

# ── find the next incomplete wave ─────────────────────────────────────────────
NEXT_WAVE="$(oc_next_incomplete_wave 2>/dev/null)"

if [[ -z "$NEXT_WAVE" ]]; then
  # All 5 waves passed in state file, but overall goal did not pass yet
  # (interview/workforce/closeout still pending). Use resume-onboarding.sh for that.
  log "All waves passed in state file — overall goal not yet met (interview/workforce/closeout pending)"
  log "Deferring to resume-onboarding.sh for remainder of overall goal"
  # Fall through to resume dispatch below with wave="overall"
  NEXT_WAVE="overall"
fi

# ── per-wave cheap check ──────────────────────────────────────────────────────
WAVE_GOAL_PASSED=0
STRIKES=0
WAVE_STATUS_SUMMARY=""

if [[ "$NEXT_WAVE" =~ ^[12345]$ ]]; then
  log "CHEAP-CHECK: running oc_wave_goal_check $NEXT_WAVE"
  oc_wave_goal_check "$NEXT_WAVE" 2>/dev/null && WAVE_GOAL_PASSED=1

  STRIKES=$(oc_wave_fail_strikes "$NEXT_WAVE" 2>/dev/null || echo 0)
  WAVE_STATUS_SUMMARY=$(oc_wave_skills_status "$NEXT_WAVE" 2>/dev/null || echo "")

  log "Wave $NEXT_WAVE: goal_passed=$WAVE_GOAL_PASSED strikes=$STRIKES skills=$WAVE_STATUS_SUMMARY"
fi

# ── 3-STRIKE escalation ───────────────────────────────────────────────────────
if [[ "$NEXT_WAVE" =~ ^[12345]$ ]] && (( STRIKES >= MAX_STRIKES )); then
  _op_chat="$(resolve_operator_chat_id)"
  log "3-STRIKE ESCALATION: wave $NEXT_WAVE has $STRIKES consecutive check failures — halting loop"

  _esc_msg="⚠️ [WATCHDOG] Onboarding loop HALTED on $(hostname): Wave ${NEXT_WAVE} has failed its goal check ${STRIKES} consecutive times (${MAX_STRIKES}-strike limit reached). Skills status: ${WAVE_STATUS_SUMMARY:-unknown}. State file: ${STATE_FILE}. ACTION NEEDED: investigate the failing skills for wave ${NEXT_WAVE}, fix them, then re-register the watchdog cron: bash ~/.openclaw/scripts/watchdog-onboarding-loop.sh (or run install.sh --resume)."

  if [[ -n "$_op_chat" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram -t "$_op_chat" -m "$_esc_msg" 2>>"$LOG_FILE" || true
    log "Escalation Telegram sent to $_op_chat"
  fi

  log "3-STRIKE: halting watchdog (self-removing cron). Operator must restart after fixing."
  self_remove_cron "3-strike-escalation"
  exit 0
fi

# ── if wave already passed, re-run overall check ──────────────────────────────
if [[ "$WAVE_GOAL_PASSED" -eq 1 ]]; then
  log "Wave $NEXT_WAVE goal PASSED — re-checking overall goal"
  oc_overall_goal_check 2>/dev/null && {
    log "OVERALL GOAL PASSED after wave $NEXT_WAVE — self-removing cron"
    self_remove_cron "overall-goal-passed-post-wave"
    exit 0
  }
  # Progress ping: wave completed
  _owner_chat=""
  command -v python3 >/dev/null 2>&1 && \
    _owner_chat=$(python3 -c "import json,os; s=json.load(open(os.environ['STATE_FILE'])); print(s.get('ownerChat',''))" STATE_FILE="$STATE_FILE" 2>/dev/null || echo "")
  [[ -z "$_owner_chat" || "$_owner_chat" == "null" ]] && _owner_chat="$(resolve_operator_chat_id)"
  if [[ -n "$_owner_chat" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram -t "$_owner_chat" \
      -m "✅ Wave ${NEXT_WAVE} of 5 complete — all skills verified. Moving on to the next wave." \
      2>>"$LOG_FILE" || true
    log "Progress ping: Wave $NEXT_WAVE complete"
  fi
  # Move to next incomplete wave
  NEXT_WAVE="$(oc_next_incomplete_wave 2>/dev/null)"
  [[ -z "$NEXT_WAVE" ]] && NEXT_WAVE="overall"
fi

# ── FURNACE GATE: interview check + wave backoff + shared dispatch lock ───────
# Pre-interview boxes must NOT hammer the model on every watchdog fire.
# Rules:
#   1. "overall" wave with interview NOT complete → defer to interview-nudge cron.
#   2. Waves 1–3: apply a 30-min backoff so model calls fire at most every 30 min
#      (not every 10/20 min), since wave 1-3 are skill-installs and don't need
#      constant prodding.
#   3. Shared dispatch lock: if resume-onboarding.sh fired a call <8 min ago, skip.

_wf_state="$WS/.workforce-build-state.json"
_interview_complete="false"
[[ -f "$_wf_state" ]] && _interview_complete="$(jq -r '.interviewComplete // false' "$_wf_state" 2>/dev/null || echo false)"

# Rule 0 (NEW — nudge lifecycle): if nudge state is DORMANT, the box is quiet.
# The watchdog obeys dormant too — no model call while dormant, even for waves.
# Re-arm (owner engagement) is detected by resume-onboarding.sh's cheap check;
# once re-armed the dormant flag is cleared and the watchdog resumes normally.
_nudge_dormant="$(nudge_get dormant)"
if [[ "$_nudge_dormant" == "true" ]]; then
  log "FURNACE-GATE: nudge-lifecycle DORMANT — no autonomous model call this cycle. Waiting for owner re-engagement (touch $NUDGE_REARM_FILE to re-arm)."
  exit 0
fi

# Rule 1: overall goal not met + interview not complete → interview-nudge owns this.
if [[ "$NEXT_WAVE" == "overall" ]] && [[ "$_interview_complete" != "true" ]]; then
  log "FURNACE-GATE: NEXT_WAVE=overall but interview not complete. interview-nudge cron owns the nudge interval. Watchdog exiting — no model call."
  exit 0
fi

# Rule 2: early-wave backoff — waves 1-3 get a 30-min minimum between dispatches.
_WATCHDOG_DISPATCH_TS="$WS/.watchdog-last-dispatch.ts"
_now_ts=$(date +%s)
if [[ "$NEXT_WAVE" =~ ^[123]$ ]]; then
  _last_dispatch=0
  [[ -f "$_WATCHDOG_DISPATCH_TS" ]] && _last_dispatch="$(cat "$_WATCHDOG_DISPATCH_TS" 2>/dev/null | tr -dc '0-9' || echo 0)"
  _gap=$(( _now_ts - _last_dispatch ))
  if (( _gap < 1800 )); then
    log "FURNACE-GATE: Wave ${NEXT_WAVE} (early-wave), last dispatch ${_gap}s ago (<1800/30min) — backoff; no model call."
    exit 0
  fi
  log "FURNACE-GATE: Wave ${NEXT_WAVE}, last dispatch ${_gap}s ago (>=1800) — allowing dispatch."
fi

# Rule 3: shared dispatch lock — if resume-onboarding.sh fired in last 8 min, skip.
if [[ -f "$SHARED_DISPATCH_LOCK" ]]; then
  _sdl_mtime=$(stat -c %Y "$SHARED_DISPATCH_LOCK" 2>/dev/null || stat -f %m "$SHARED_DISPATCH_LOCK" 2>/dev/null || echo 0)
  _sdl_age=$(( _now_ts - _sdl_mtime ))
  if (( _sdl_age < 480 )); then
    log "SHARED-DISPATCH-LOCK: resume-onboarding.sh dispatched ${_sdl_age}s ago (<480) — skipping watchdog fire to avoid double model call."
    exit 0
  fi
fi

# ── build the EXACT resume prompt for the next incomplete wave ────────────────
build_wave_prompt() {
  local wave="$1"
  local skills_status="$2"
  local prompt=""

  case "$wave" in
    1) prompt="[ONBOARDING-WATCHDOG] Wave 1 (FOUNDATION) is incomplete. Skills: ${skills_status}. Wave 1 skills are: 01-teach-yourself-protocol, 02-back-yourself-up-protocol. These are REQUIRED before any other wave. DO THIS NOW: (1) source ~/.openclaw/scripts/onboarding-state.sh; (2) for each Wave 1 skill not qc-passed: read ALL .md files in the skill folder, execute INSTALL.md steps, merge CORE_UPDATES.md, run oc_gate_skill <folder>; (3) loop until both are qc-passed; (4) confirm wave 1 goal: bash ~/.openclaw/scripts/watchdog-onboarding-loop.sh will check automatically. Do NOT proceed to Wave 2 until Wave 1 is qc-passed." ;;
    2) prompt="[ONBOARDING-WATCHDOG] Wave 2 (INDEPENDENT INTEGRATIONS) is incomplete. Skills: ${skills_status}. Wave 2 skills: 03-agent-browser, 04-superpowers, 05-ghl-setup, 06-ghl-install-pages, 07-kie-setup, 08-vercel-setup, 09-context7, 10-github-setup, 11-superdesign, 12-openrouter-setup, 14-google-workspace-integration. DO THIS NOW: (1) source ~/.openclaw/scripts/onboarding-state.sh; (2) install all not-qc-passed skills in PARALLEL (up to 10 concurrent on Mac, 5 on VPS): for each skill read ALL .md files, execute INSTALL.md, merge CORE_UPDATES.md, run oc_gate_skill <folder>; (3) send owner progress update; (4) once all Wave 2 skills are qc-passed, proceed to Wave 3." ;;
    3) prompt="[ONBOARDING-WATCHDOG] Wave 3 (CONTENT + SERVICE TOOLS) is incomplete. Skills: ${skills_status}. Wave 3 skills: 15-blackceo-team-management, 16-summarize-youtube, 17-self-improving-agent, 18-proactive-agent, 19-humanizer, 20-youtube-watcher, 21-tavily-search, 24-storyboard-writer, 25-video-creator, 26-caption-creator, 27-video-editor, 28-cinematic-forge, 29-ghl-convert-and-flow, 30-fish-audio-api-reference, 43-graphify-knowledge-graph. DO THIS NOW: install all not-qc-passed skills in parallel (up to 10/5 concurrent). For each skill: read ALL .md files, execute INSTALL.md, merge CORE_UPDATES.md, run oc_gate_skill. Send owner update when wave 3 is complete." ;;
    4) prompt="[ONBOARDING-WATCHDOG] Wave 4 (INFRASTRUCTURE) is incomplete. Skills: ${skills_status}. Wave 4 skills: 31-upgraded-memory-system, 36-ghl-mcp-setup (SEQUENTIAL — Memory first, then MCP). DO THIS NOW: (1) install 31-upgraded-memory-system (memory architecture must be ready before persona/CC); (2) install 36-ghl-mcp-setup; (3) verify both qc-passed via oc_gate_skill." ;;
    5) prompt="[ONBOARDING-WATCHDOG] Wave 5 (USER-INTERACTION-AWARE) is incomplete. Skills: ${skills_status}. Wave 5 skills: 22-book-to-persona-coaching-leadership-system, 23-ai-workforce-blueprint, 32-command-center-setup, 35-social-media-planner (SEQUENTIAL). DO THIS NOW via SUB-AGENT DISPATCH: (1) dispatch sub-agent for Skill 22 (persona — interview-pending is a LEGITIMATE park, ask owner if needed); (2) after 22 passes, dispatch sub-agent for Skill 23 (workforce blueprint — surfaces owner interview via triple-fire trigger); (3) after 23, dispatch sub-agent for Skill 32 (command center); (4) dispatch sub-agent for Skill 35 (social planner). Each skill can park at interview-pending — that counts as wave-goal-passed for Wave 5." ;;
    overall) prompt="[ONBOARDING-WATCHDOG] All 5 waves are complete but the OVERALL GOAL is not yet met. Run: bash ~/.openclaw/scripts/resume-onboarding.sh to check what's still pending (interview, workforce build, closeout). The overall goal requires: all waves verified (done) + interview complete + workforce built (buildCompletedAt set in .workforce-build-state.json) + closeout delivered (closeoutStatus=done). Check each of these and complete any that are missing." ;;
    *) prompt="[ONBOARDING-WATCHDOG] Onboarding state is incomplete. Run: bash ~/.openclaw/scripts/resume-onboarding.sh to check what needs to be done." ;;
  esac
  printf '%s' "$prompt"
}

# ── resolve target chat ───────────────────────────────────────────────────────
_owner_chat=""
command -v python3 >/dev/null 2>&1 && \
  _owner_chat=$(python3 -c "
import json,os
try:
    s=json.load(open(os.environ.get('STATE_FILE','')))
    print(s.get('ownerChat',''))
except: pass
" STATE_FILE="$STATE_FILE" 2>/dev/null || echo "")
[[ -z "$_owner_chat" || "$_owner_chat" == "null" ]] && _owner_chat="$(resolve_operator_chat_id)"

if [[ -z "$_owner_chat" ]]; then
  log "no usable target chat — cannot dispatch resume; exiting"
  exit 0
fi

# ── dispatch the EXACT wave resume prompt ────────────────────────────────────
SKILLS_STATUS="$(oc_wave_skills_status "$NEXT_WAVE" 2>/dev/null || echo "")"
RESUME_MSG="$(build_wave_prompt "$NEXT_WAVE" "$SKILLS_STATUS")"

log "Dispatching wave-$NEXT_WAVE resume prompt to $_owner_chat"

if command -v openclaw >/dev/null 2>&1; then
  _WD_SEND_OUT="$(mktemp)"
  _WD_SEND_RC=0
  openclaw message send --channel telegram -t "$_owner_chat" \
    -m "$RESUME_MSG" >"$_WD_SEND_OUT" 2>&1 || _WD_SEND_RC=$?

  if [[ "$_WD_SEND_RC" -eq 0 ]]; then
    log "dispatched wave-$NEXT_WAVE resume prompt (strikes=$STRIKES)"
    # Stamp shared dispatch lock (dedup with resume-onboarding.sh)
    touch "$SHARED_DISPATCH_LOCK" 2>/dev/null || true
    # Stamp per-wave dispatch timestamp (early-wave 30-min backoff)
    echo "$_now_ts" > "$_WATCHDOG_DISPATCH_TS" 2>/dev/null || true
    # Send Telegram progress ping to operator (separate from agent message)
    _op_chat="$(resolve_operator_chat_id)"
    if [[ "$_op_chat" != "$_owner_chat" ]] && [[ -n "$_op_chat" ]]; then
      openclaw message send --channel telegram -t "$_op_chat" \
        -m "[WATCHDOG] Onboarding on $(hostname): resuming Wave ${NEXT_WAVE} (strike ${STRIKES}/${MAX_STRIKES}). Skills: ${SKILLS_STATUS:-checking...}." \
        2>>"$LOG_FILE" || true
    fi
  else
    _WD_SEND_CONTENT="$(cat "$_WD_SEND_OUT" 2>/dev/null || true)"
    log "FAILED to dispatch wave-$NEXT_WAVE resume prompt to $_owner_chat (rc=${_WD_SEND_RC}): ${_WD_SEND_CONTENT}"
    # Credit-failure backoff: 402 (payment required) or 429 (rate/quota).
    # Enter DORMANT immediately — do NOT retry-storm. Notify operator ONCE.
    if [[ "$_WD_SEND_CONTENT" == *"402"* || "$_WD_SEND_CONTENT" == *"429"* || \
          "${ONBOARDING_LAST_SEND_RC:-}" == "402" || "${ONBOARDING_LAST_SEND_RC:-}" == "429" ]]; then
      nudge_credit_fail_dormant
      log "NUDGE-LIFECYCLE[watchdog]: credit-failure — DORMANT entered; no further autonomous retries."
    fi
  fi
  rm -f "$_WD_SEND_OUT" 2>/dev/null || true
else
  log "openclaw CLI not found — cannot dispatch; will retry next fire"
fi

exit 0
