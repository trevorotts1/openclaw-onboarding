#!/usr/bin/env bash
# resume-closeout-cron.sh — PRD-2.8: DEDICATED closeout resume cron.
#
# This is a SEPARATE cron from the workforce-build-resume cron (Skill 23).
# It is registered by run-closeout.sh when closeoutStatus transitions to
# "generating" (if not already registered) and by the installer. It fires
# every 15 minutes until ALL 7 closeout deliverable legs are done|waived.
#
# KILL CONDITION (loop doctrine):
#   Self-removes when closeoutStatus == "done" OR partial with no resumable legs,
#   OR when all 7 closeoutDeliverables are done|waived.
#   Also self-removes after ZHC_CLOSEOUT_MAX_CRON_RUNS (default 48, i.e. 12h at
#   15-min intervals). After exhaustion, escalates to operator and stops.
#   This prevents an unbounded loop if something is fundamentally broken.
#
# NO-PROGRESS GIVE-UP PAUSE (v11.11.0 / fix/cron-nudge-sweep-selfheal):
#   The MAX_RUNS cap above is blunt (12h of heavy re-runs before giving up) and
#   never distinguishes "the build is still working" from "this is wedged on a
#   HUMAN action that re-running can never clear" (client never shared the Notion
#   page, interviewQc awaiting a human → blocked-interview-incomplete, an unmet
#   floor/library → blocked-*-incomplete, a leg failing identically every fire).
#   On those boxes every 15-min fire re-launches the MODEL+API-heavy
#   run-closeout.sh for nothing — on a paid provider that is real money burned.
#   So: fingerprint the blocking state from the cheap reads already in hand
#   (closeoutStatus + blockReason + notion leg + interviewQc + legs-done count).
#   If the fingerprint is UNCHANGED across ZHC_CLOSEOUT_MAX_STALL_PASSES (default
#   4 = 1h) consecutive fires AND the box is in a recognised blocked/stuck state,
#   STOP dispatching run-closeout.sh: escalate ONCE to the operator (idempotent)
#   and PAUSE. The cron stays alive doing ONLY the token-free check; the instant
#   the fingerprint changes (the human shares the page / QC is approved / the
#   build advances) the stall counter resets and heavy dispatch resumes
#   automatically. No work is abandoned — it is parked pending the human.
#
# TRIGGER CHECK (cheap, token-free):
#   Reads .closeoutStatus + .closeoutDeliverables from the state file. Only
#   invokes the agent (expensive) when it detects incomplete work. The check
#   itself costs zero tokens.
#
# LOOP REGISTRY:
#   Writes its cron UUID to .closeoutResumeUuid in state so the self-remove
#   can find and kill it. The closeout's successful done-transition calls
#   self_remove_cron() before writing done.
#
# PRD-2.8 / v11.11.0

set -u

# ---- platform detection — via the shared resolver (false-negative #3 fix) ----
# Centralized /data-else-HOME .openclaw detection; identical inline fallback if
# the shared file is absent. See shared-utils/resolve-oc-root.sh.
_OC_ROOT_RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../shared-utils/resolve-oc-root.sh"
# shellcheck source=/dev/null
[[ -f "$_OC_ROOT_RESOLVER" ]] && source "$_OC_ROOT_RESOLVER"
if declare -F resolve_oc_root >/dev/null 2>&1; then
  if _oc_root_resolved="$(resolve_oc_root)"; then
    OC_ROOT="$_oc_root_resolved"
  else
    echo "[resume-closeout-cron] no OpenClaw root found; aborting" >&2
    exit 0
  fi
elif [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[resume-closeout-cron] no OpenClaw root found; aborting" >&2
  exit 0
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOCK_FILE="$OC_ROOT/workspace/.closeout-resume.lock"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
RUN_COUNT_FILE="$OC_ROOT/workspace/.closeout-resume-runs.count"
MAX_RUNS="${ZHC_CLOSEOUT_MAX_CRON_RUNS:-48}"
STALE_LOCK_MINUTES=20

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"
}

state_get() {
  jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null
}

# SK1-13: shared, concurrency-safe state_set (portable mkdir-mutex + stale-lock
# breaker) replaces the former unlocked jq->tmp->mv copy. This cron writes state
# while a still-running (nohup'd) run-closeout.sh writes the SAME file; the shared
# lock serializes those read-modify-writes so neither can lost-update the other.
# shellcheck source=lib-closeout-state.sh disable=SC1090,SC1091
if ! source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-closeout-state.sh" 2>/dev/null; then
  # Fallback for an older bundle without the shared lib: unlocked atomic write.
  state_set() {
    local tmp
    tmp=$(mktemp)
    if jq "$1" "$STATE_FILE" > "$tmp"; then
      mv "$tmp" "$STATE_FILE"
    else
      rm -f "$tmp"
      log "state_set failed for: $1"
      return 1
    fi
  }
fi

# ---- run count (defense-in-depth cap) ----
run_count=0
if [[ -f "$RUN_COUNT_FILE" ]]; then
  run_count=$(cat "$RUN_COUNT_FILE" 2>/dev/null | tr -d '[:space:]' | grep -E '^[0-9]+$' || echo 0)
fi
run_count=$((run_count + 1))
printf '%d\n' "$run_count" > "$RUN_COUNT_FILE"

# ---- resolve operator ESCALATION chat for escalations ----
# CO-MINGLING GUARD (v12.4.0): destination is OPT-IN. NO hardcoded personal chat.
# Empty result = escalation destination not configured; callers MUST skip the send.
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_ESCALATION_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    if [[ -z "$v" ]]; then
      v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
      case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    fi
  fi
  [[ -z "$v" && -n "${OPERATOR_ESCALATION_CHAT_ID:-}" ]] && v="$OPERATOR_ESCALATION_CHAT_ID"
  [[ -z "$v" && -n "${ZHC_OPERATOR_CHAT_ID:-}" ]] && v="$ZHC_OPERATOR_CHAT_ID"
  # No baked-in personal chat. Empty = no operator escalation configured.
  printf '%s' "$v"
}

# ---- self-remove this cron by UUID ----
find_self_cron_uuid() {
  # First check state file (registered UUID)
  if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
    uuid=$(state_get '.closeoutResumeUuid')
    [[ -n "$uuid" && "$uuid" != "null" ]] && printf '%s' "$uuid" && return 0
  fi
  # Fallback: scan openclaw cron list
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/closeout-resume/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}

self_remove_cron() {
  local reason="$1"
  local uuid
  uuid=$(find_self_cron_uuid)
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not find closeout-resume cron UUID"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if command -v openclaw >/dev/null 2>&1; then
    openclaw cron rm "$uuid" 2>>"$LOG_FILE" || log "cron rm failed (tolerated)"
  fi
  # Clear the UUID from state
  state_set 'del(.closeoutResumeUuid) | .closeoutResumeRegisteredAt = null' 2>/dev/null || true
}

# ---- lockfile (prevent double-fire) ----
if [[ -f "$LOCK_FILE" ]]; then
  lock_age=$(( $(date -u +%s) - $(date -u -r "$LOCK_FILE" +%s 2>/dev/null || date -u +%s) ))
  if (( lock_age < STALE_LOCK_MINUTES * 60 )); then
    log "lockfile held ($lock_age s old, limit=${STALE_LOCK_MINUTES}m) — closeout may still be running; skip"
    exit 0
  fi
  log "stale lockfile removed ($lock_age s old)"
  rm -f "$LOCK_FILE"
fi
touch "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ---- no state file → nothing to do ----
if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE -- nothing to do"
  exit 0
fi

command -v jq >/dev/null 2>&1 || { log "jq not found -- aborting"; exit 1; }

# ---- check if this cron should still be alive ----
closeout_status=$(state_get '.closeoutStatus')
build_completed=$(state_get '.buildCompletedAt')

# Kill condition 1: build not complete → not our job
if [[ -z "$build_completed" || "$build_completed" == "null" ]]; then
  log "buildCompletedAt not set -- build not done yet; nothing to resume"
  exit 0
fi

# Kill condition 2: already done or sent
if [[ "$closeout_status" == "done" || "$closeout_status" == "sent" ]]; then
  log "closeoutStatus=$closeout_status -- complete; self-removing cron (kill condition met)"
  self_remove_cron "closeout complete ($closeout_status)"
  exit 0
fi

# Kill condition 3: max runs cap
if (( run_count > MAX_RUNS )); then
  reason="closeout did not complete after $MAX_RUNS cron fires (${MAX_RUNS}×15min = $((MAX_RUNS*15/60))h)"
  log "MAX RUNS EXCEEDED ($run_count > $MAX_RUNS): $reason -- removing cron + escalating"
  operator_chat=$(resolve_operator_chat_id)
  if [[ -n "$operator_chat" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram --target "$operator_chat" \
      --message "🚨 Closeout resume cron exhausted ($run_count runs). closeoutStatus=${closeout_status:-unset}. State: $STATE_FILE" \
      >/dev/null 2>&1 || true
  else
    log "operator escalation chat not configured -- skipping operator notify (state already logged)"
  fi
  self_remove_cron "max-runs-exceeded ($run_count)"
  exit 0
fi

# ---- check all 7 PRD-2.8 deliverable legs ----
# Cheap token-free check. Deliverable fields mirror closeoutDeliverables in schema.
check_leg() {
  local val
  val=$(state_get "$1")
  [[ -n "$val" && "$val" != "null" && "$val" != "false" ]]
}

inf1_done=0; inf2_done=0; video_done=0; notion_done=0
tg_done=0; cc_done=0; n8n_done=0

check_leg '.infographic1Url'                            && inf1_done=1
check_leg '.infographic2Url'                            && inf2_done=1
check_leg '.celebrationVideoUrl'                        && video_done=1
check_leg '.notionRootPageUrl'                          && notion_done=1
check_leg '.closeoutDeliverables.telegramSequenceSent'  && tg_done=1
check_leg '.closeoutDeliverables.ccUrlDelivered'        && cc_done=1
n8n_val=$(state_get '.closeoutDeliverables.n8nWired')
[[ "$n8n_val" == "true" || "$n8n_val" == "1" || "$n8n_val" == "skipped" ]] && n8n_done=1

total_done=$(( inf1_done + inf2_done + video_done + notion_done + tg_done + cc_done + n8n_done ))
log "leg status: inf1=$inf1_done inf2=$inf2_done video=$video_done notion=$notion_done tg=$tg_done cc=$cc_done n8n=$n8n_done (${total_done}/7)"

# ----------------------------------------------------------------------
# BUG A FIX (GHOST FALSE-DONE).
#
# Through v12.x "Kill condition 4" stamped closeoutStatus=done the moment 7
# URL/flag fields were non-null. That bypassed EVERY finalize guard in
# run-closeout.sh (phantom-closeout guard + the Telegram delivery-confirmation
# gate). The observed ghost: run-closeout.sh recorded
#   closeout finalize: critical-failed: infographic-1,telegram   (08:51, exit 1)
# and 6 minutes later THIS cron stamped done (08:57) because the URL fields were
# present — even though the critical legs had FAILED. closeoutStatus=done may now
# be written by this cron ONLY when ALL critical legs are VERIFIED:
#   * every load-bearing deliverable exists, AND
#   * every REQUIRED Telegram slot has a gateway-confirmed messageId AND passes
#     verify-telegram-delivery.sh (same gate run-closeout.sh uses).
# On any critical failure we stamp partial (named pending slots) — NEVER done.
# ----------------------------------------------------------------------

# GUARD: never re-stamp done over a recorded critical failure that hasn't been
# cleared by a fresh successful run. If a prior run-closeout finalize recorded
# closeoutStatus=failed (a CRITICAL failure) or a critical entry in
# closeoutCriticalFailed, this cron must NOT overwrite it to done — it may only
# re-launch the build (the in-process exec below) and let run-closeout's own
# verified finalize transition it. We treat closeoutStatus=failed as a sticky
# critical marker: the only legitimate path out of it is run-closeout.sh writing
# a fresh verified done/partial itself.
critical_failed_recorded=0
if [[ "$closeout_status" == "failed" ]]; then
  critical_failed_recorded=1
  log "GUARD: closeoutStatus=failed is a recorded critical failure (reason: $(state_get '.closeoutFailureReason')). This cron will NOT stamp done over it -- only run-closeout.sh's verified finalize may clear it. Proceeding to re-launch the build."
fi

# verify_critical_legs -> 0 if every critical leg is verified, else non-zero.
# Mirrors run-closeout.sh finalize: load-bearing deliverables + telegram
# delivery confirmed against the gateway (not just "a URL is set").
critical_pending=""
verify_critical_legs() {
  critical_pending=""
  # Load-bearing deliverable 1: org chart artifact present.
  if ! check_leg '.infographic1Url'; then
    critical_pending="${critical_pending},infographic1"
  fi
  # Load-bearing deliverable 2: at least one Telegram message with a REAL
  # gateway-confirmed messageId (a bare send-failed slot must not count).
  local delivered_count
  delivered_count=$(jq -r '(.messagesDelivered // []) | map(select((.messageId // "") | tostring | length > 0)) | length' "$STATE_FILE" 2>/dev/null)
  if [[ -z "$delivered_count" || "$delivered_count" == "null" || "$delivered_count" == "0" ]]; then
    critical_pending="${critical_pending},telegramSequence"
  fi
  # Telegram delivery-confirmation gate: cross-check captured messageIds against
  # the gateway sent-registry (same anti-faking layer run-closeout.sh uses).
  local verify_tg=""
  for _vc in \
    "$OC_ROOT/skills/37-zhc-closeout/scripts/verify-telegram-delivery.sh" \
    "$HOME/.openclaw/skills/37-zhc-closeout/scripts/verify-telegram-delivery.sh" \
    "/data/.openclaw/skills/37-zhc-closeout/scripts/verify-telegram-delivery.sh"; do
    [[ -f "$_vc" ]] && verify_tg="$_vc" && break
  done
  if [[ -n "$verify_tg" ]]; then
    if ! ZHC_STATE_FILE="$STATE_FILE" ZHC_LOG_FILE="$LOG_FILE" bash "$verify_tg" >>"$LOG_FILE" 2>&1; then
      # Only add telegramSequence once.
      case ",$critical_pending," in *,telegramSequence,*) : ;; *) critical_pending="${critical_pending},telegramSequence" ;; esac
    fi
  else
    # Verifier missing: refuse to claim done (same stance as run-closeout.sh).
    case ",$critical_pending," in *,telegramSequence,*) : ;; *) critical_pending="${critical_pending},telegramSequence-unverifiable" ;; esac
  fi
  critical_pending="${critical_pending#,}"
  [[ -z "$critical_pending" ]]
}

# Kill condition 4: all 7 legs present AND critical legs VERIFIED.
if (( total_done == 7 )); then
  if (( critical_failed_recorded == 1 )); then
    log "all 7 leg fields are present, but closeoutStatus=failed is recorded -- REFUSING to stamp done (ghost-closeout guard). Re-launching run-closeout.sh so its verified finalize decides."
  elif verify_critical_legs; then
    log "all 7 closeout deliverable legs present AND critical legs VERIFIED (telegram confirmed, org-chart present) -- marking closeoutStatus=done and self-removing cron"
    state_set '.closeoutStatus = "done" | .closeoutCompletedAt = (now | strftime("%Y-%m-%dT%H:%M:%SZ")) | .closeoutPendingSlots = []' || true
    self_remove_cron "all-7-legs-done-verified"
    exit 0
  else
    log "all 7 leg FIELDS present but CRITICAL legs UNVERIFIED (pending: ${critical_pending}) -- stamping partial, NOT done (ghost-closeout guard). Re-launching run-closeout.sh."
    state_set ".closeoutStatus = \"partial\" | .closeoutPendingSlots = (\"${critical_pending}\" | split(\",\")) | .closeoutPartialReason = \"resume-cron critical-unverified: ${critical_pending}\"" || true
  fi
fi

# ----------------------------------------------------------------------
# NO-PROGRESS GIVE-UP PAUSE (v11.11.0). Token-free. Runs BEFORE the heavy
# run-closeout.sh dispatch below so a wedged box burns ZERO model/API tokens.
# See the KILL CONDITION / NO-PROGRESS header block for the full rationale.
# ----------------------------------------------------------------------
MAX_STALL_PASSES="${ZHC_CLOSEOUT_MAX_STALL_PASSES:-4}"

# Cheap recognised-blocker test (token-free). True when re-running the heavy
# build cannot, by itself, clear the current state — only a human (or an
# external change) can: a blocked-* floor/library/interview/wiring gate, a hard
# failure, a stalled partial, the client never sharing the Notion page, or
# interview QC awaiting a human verdict.
_is_human_or_stuck_blocker() {
  case "$closeout_status" in
    blocked-floor-incomplete|blocked-libraries-incomplete|blocked-interview-incomplete|blocked-qc-pending|blocked-wiring-incomplete|failed|partial)
      return 0 ;;
  esac
  local _notion_leg; _notion_leg=$(state_get '.closeoutLegStatus.notion')
  case "$_notion_leg" in failed:no-shared-page) return 0 ;; esac
  local _iqc; _iqc=$(state_get '.interviewQc.status')
  case "$_iqc" in pending|needs-review) return 0 ;; esac
  return 1
}

# Fingerprint everything that would indicate progress (all reads are token-free).
_stall_fp="${closeout_status:-none}|$(state_get '.closeoutBlockReason')|$(state_get '.closeoutLegStatus.notion')|$(state_get '.interviewQc.status')|${total_done}"
_prev_fp=$(state_get '.closeoutResumeStallFingerprint')
_stall_passes=$(state_get '.closeoutResumeStallPasses')
[[ "$_stall_passes" =~ ^[0-9]+$ ]] || _stall_passes=0

if [[ "$_stall_fp" == "$_prev_fp" ]]; then
  _stall_passes=$((_stall_passes + 1))
  state_set ".closeoutResumeStallPasses = ${_stall_passes}" 2>/dev/null || true
else
  # Progress (or first observation): reset the counter, record the new
  # fingerprint, and clear any active pause so heavy dispatch resumes (a future
  # stall then re-escalates exactly once).
  _stall_passes=0
  state_set ".closeoutResumeStallFingerprint = \"${_stall_fp}\" | .closeoutResumeStallPasses = 0 | .closeoutResumePaused = false | .closeoutResumePausedNotifiedAt = null" 2>/dev/null || true
  if [[ -n "$_prev_fp" && "$_prev_fp" != "null" ]]; then
    log "progress detected (state fingerprint changed) -- stall counter reset; normal closeout dispatch continues"
  fi
fi

if (( _stall_passes >= MAX_STALL_PASSES )) && _is_human_or_stuck_blocker; then
  log "NO-PROGRESS PAUSE: blocker unchanged for ${_stall_passes} fires (cap=${MAX_STALL_PASSES}); closeoutStatus=${closeout_status:-unset}, blockReason=$(state_get '.closeoutBlockReason'), notionLeg=$(state_get '.closeoutLegStatus.notion'), interviewQc=$(state_get '.interviewQc.status'). This needs a HUMAN action -- re-running the build cannot clear it. SKIPPING heavy run-closeout.sh dispatch (zero model burn); pausing until the state changes."
  # Escalate ONCE per pause (idempotent on the notifiedAt marker). The cron stays
  # registered and keeps doing the cheap check, so it auto-resumes when the human acts.
  _paused_notified=$(state_get '.closeoutResumePausedNotifiedAt')
  if [[ -z "$_paused_notified" || "$_paused_notified" == "null" ]]; then
    operator_chat=$(resolve_operator_chat_id)
    _agent_nm=$(state_get '.agentName'); [[ -z "$_agent_nm" || "$_agent_nm" == "null" ]] && _agent_nm="client"
    if [[ -n "$operator_chat" ]] && command -v openclaw >/dev/null 2>&1; then
      openclaw message send --channel telegram --target "$operator_chat" \
        --message "⏸️ ZHC closeout PAUSED (awaiting human action) for ${_agent_nm}. closeoutStatus=${closeout_status:-unset}. Reason: $(state_get '.closeoutBlockReason')$(state_get '.notionFailureReason'). The resume cron stopped re-running the model and will auto-continue when the blocker clears. State: $STATE_FILE" \
        >/dev/null 2>&1 || true
    else
      log "operator escalation chat not configured -- pause logged only (no operator notify; state marker written)"
    fi
    state_set ".closeoutResumePaused = true | .closeoutResumePausedReason = \"no-progress: ${closeout_status:-unset}\" | .closeoutResumePausedNotifiedAt = \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" 2>/dev/null || true
  fi
  log "resume cron fire complete (PAUSED awaiting human, run $run_count/$MAX_RUNS, stall=${_stall_passes}) -- no heavy dispatch"
  exit 0
fi

# ---- work to do: dispatch CLOSEOUT-RESUME self-ping ----
# Resolve the agent's owner chat and the operator's chat
owner_chat=$(state_get '.ownerChat')
agent_name=$(state_get '.agentName // "CEO"')
operator_chat=$(resolve_operator_chat_id)
incomplete_legs=""
[[ "$inf1_done"  -eq 0 ]] && incomplete_legs="${incomplete_legs},infographic1"
[[ "$inf2_done"  -eq 0 ]] && incomplete_legs="${incomplete_legs},infographic2"
[[ "$video_done" -eq 0 ]] && incomplete_legs="${incomplete_legs},celebrationVideo"
[[ "$notion_done" -eq 0 ]] && incomplete_legs="${incomplete_legs},notionTree"
[[ "$tg_done"    -eq 0 ]] && incomplete_legs="${incomplete_legs},telegramSequence"
[[ "$cc_done"    -eq 0 ]] && incomplete_legs="${incomplete_legs},ccUrl"
[[ "$n8n_done"   -eq 0 ]] && incomplete_legs="${incomplete_legs},n8nWired"
incomplete_legs="${incomplete_legs#,}"  # strip leading comma

# Escalate to operator after 3 consecutive resume attempts (not total runs)
attempts=$(state_get '.closeoutResumeAttempts // 0')
attempts=$((attempts + 1))
state_set ".closeoutResumeAttempts = $attempts" || true

if (( attempts >= 3 )) && [[ $(( attempts % 3 )) -eq 0 ]]; then
  log "closeout has been resumed $attempts times without completion -- escalating to operator"
  if [[ -n "$operator_chat" ]] && command -v openclaw >/dev/null 2>&1; then
    openclaw message send --channel telegram --target "$operator_chat" \
      --message "⚠️ ZHC closeout stalled for ${agent_name}. Missing legs: ${incomplete_legs}. closeoutStatus=${closeout_status:-unset}. Resume attempt $attempts. Check: $LOG_FILE" \
      >/dev/null 2>&1 || true
  else
    log "operator escalation chat not configured -- skipping operator notify (state already logged)"
  fi
fi

# PRD-FINAL-PACKAGE Step 1 (v12.6.0): DETERMINISTIC in-process exec of run-closeout.sh.
# This is the PRIMARY path. The self-ping below is SECONDARY (fallback only).
# run-closeout.sh is idempotent -- a double-fire is safe.
_CLOSEOUT_SCRIPT=""
for _cand in \
  "$OC_ROOT/skills/37-zhc-closeout/scripts/run-closeout.sh" \
  "$HOME/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh" \
  "/data/.openclaw/skills/37-zhc-closeout/scripts/run-closeout.sh"; do
  if [[ -f "$_cand" ]]; then
    _CLOSEOUT_SCRIPT="$_cand"
    break
  fi
done
if [[ -n "$_CLOSEOUT_SCRIPT" ]]; then
  log "in-process exec of run-closeout.sh (PRIMARY -- deterministic, no Telegram required)"
  nohup bash "$_CLOSEOUT_SCRIPT" >> "$LOG_FILE" 2>&1 &
  log "run-closeout.sh launched (pid=$!); self-ping follows as secondary nudge"
else
  log "WARN: run-closeout.sh not found at any expected path -- falling back to self-ping only"
fi

msg="[CLOSEOUT-RESUME] ${agent_name}: workforce closeout is incomplete after ${run_count} cron fire(s). closeoutStatus=${closeout_status:-unset}. Missing deliverable legs: ${incomplete_legs}. run-closeout.sh was launched in-process as the primary path; this self-ping is a secondary nudge. Invoke scripts/run-closeout.sh manually if the closeout does not advance within 15 min. Do NOT message the owner -- they only hear from you when Step 6 Telegram delivery fires. Resume attempt ${attempts}."

if [[ -z "$owner_chat" || "$owner_chat" == "null" ]]; then
  log "ownerChat not set -- falling back to operator escalation chat (if configured)"
  target_chat="$operator_chat"
else
  target_chat="$owner_chat"
fi

# run-closeout.sh already fired in-process above (PRIMARY path). The self-ping is
# only a secondary nudge -- if neither owner nor operator chat is available, skip
# the send rather than dispatching to an empty target.
if [[ -z "$target_chat" ]]; then
  log "[CLOSEOUT-RESUME] no usable target chat (ownerChat unset, operator escalation not configured) -- in-process exec already fired; skipping self-ping"
  exit 0
fi

log "[CLOSEOUT-RESUME] run=$run_count attempt=$attempts missing=$incomplete_legs -- dispatching self-ping to $target_chat"

if command -v openclaw >/dev/null 2>&1; then
  openclaw message send --channel telegram --target "$target_chat" --message "$msg" \
    >/dev/null 2>&1 || log "WARN: openclaw message send failed (gateway may be restarting; in-process exec already fired)"
else
  log "WARN: openclaw CLI not found -- cannot dispatch self-ping (in-process exec fired above)"
fi

log "resume cron fire complete (run $run_count/$MAX_RUNS)"
exit 0
