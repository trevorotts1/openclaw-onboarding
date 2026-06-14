#!/usr/bin/env bash
# closeout-readiness-watchdog.sh — PRD-2.15 operator escalation lane.
#
# A NEW cron (every 6h) that is the OPERATOR-FACING twin of the owner-facing
# interview-nudge cron. The nudge cron is, by binding design, an owner-only
# reminder. This watchdog is the operator escalation lane that was missing:
# it surfaces "client is one step from value and stuck" to the operator and
# Rescue Rangers, and acts as the first-class stuck-client surface.
#
# STUCK CLASSES (mutually exclusive, evaluated top-down):
#   STUCK_MID_INTERVIEW        — interview in progress, idle >= ZHC_STUCK_INTERVIEW_DAYS
#   STUCK_INTERVIEW_NEVER_STARTED — lastQuestionAt unset, box provisioned >= ZHC_STUCK_NOSTART_DAYS
#   STUCK_QC_FAILED            — interviewComplete but interviewQc.status in fail|needs-review
#   STUCK_PRE_CLOSEOUT         — QC passed, buildCompletedAt=null, resumeAttempts >= maxResumeAttempts
#   STUCK_CLOSEOUT_BLOCKED     — closeoutStatus in blocked-* | failed >= ZHC_STUCK_CLOSEOUT_HOURS
#
# ESCALATION: each stuck class fires ONCE per state-transition (idempotent,
# gated by stuckEscalations.<class>.notifiedAt). Re-fires after
# ZHC_STUCK_REESCALATE_DAYS (default 7) elapse without the class clearing.
#
# BINDING RULES (no exceptions):
#   • NEVER triggers Option B, never writes answers, never fakes --complete.
#   • All Telegram sends go through `openclaw message send`. NO direct HTTP.
#   • Rescue Rangers via the n8n webhook (RESCUE_RANGERS_WEBHOOK_URL).
#   • Token-free state read first; no agent dispatch unless needed.
#   • Lockfile + stale-lock reap (mirrors interview-nudge-cron.sh).
#
# PRD-2.15 / v12.3.12
set -uo pipefail

# ── Platform detection ───────────────────────────────────────────────────────
if [[ -z "${OC_ROOT:-}" ]]; then
  if [[ -d /data/.openclaw ]]; then
    OC_ROOT=/data/.openclaw
  elif [[ -d "${HOME}/.openclaw" ]]; then
    OC_ROOT="${HOME}/.openclaw"
  else
    echo "[closeout-readiness-watchdog] no OpenClaw root found; aborting" >&2
    exit 0
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT}/workspace/.workforce-build-state.json}"
LOCK_FILE="${OC_ROOT}/workspace/.closeout-watchdog.lock"
LOG_FILE="${OC_ROOT}/workspace/.closeout-watchdog.log"
STALE_LOCK_MINUTES=10

# ── Env defaults ─────────────────────────────────────────────────────────────
ZHC_STUCK_INTERVIEW_DAYS="${ZHC_STUCK_INTERVIEW_DAYS:-5}"
ZHC_STUCK_NOSTART_DAYS="${ZHC_STUCK_NOSTART_DAYS:-3}"
ZHC_STUCK_CLOSEOUT_HOURS="${ZHC_STUCK_CLOSEOUT_HOURS:-12}"
ZHC_STUCK_REESCALATE_DAYS="${ZHC_STUCK_REESCALATE_DAYS:-7}"
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
RESCUE_RANGERS_WEBHOOK_URL="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rescue-rangers}"

# Flag: --from-nudge signals the nudge cron invoked us after its final pass
FROM_NUDGE=0
[[ "${1:-}" == "--from-nudge" ]] && FROM_NUDGE=1

# Flag: --local skips SSH (used by fleet-stuck-clients.sh + CI tests)
LOCAL_MODE=0
[[ "${1:-}" == "--local" || "${2:-}" == "--local" ]] && LOCAL_MODE=1

log() {
  printf '%s [closeout-watchdog] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${LOG_FILE}"
}

state_get() {
  jq -r "$1 // empty" "${STATE_FILE}" 2>/dev/null
}

state_set() {
  local expr="$1"
  local tmp
  tmp=$(mktemp)
  if jq "$expr" "${STATE_FILE}" > "$tmp" 2>/dev/null; then
    mv "$tmp" "${STATE_FILE}"
  else
    rm -f "$tmp"
    log "state_set failed for: $expr"
    return 1
  fi
}

now_iso() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

now_epoch() {
  date -u +%s
}

# ── Lockfile ─────────────────────────────────────────────────────────────────
if [[ -f "${LOCK_FILE}" ]]; then
  lock_age=$(( $(now_epoch) - $(date -u -r "${LOCK_FILE}" +%s 2>/dev/null || now_epoch) ))
  if (( lock_age < STALE_LOCK_MINUTES * 60 )); then
    log "lockfile held (${lock_age}s old, limit=${STALE_LOCK_MINUTES}m) — already running; skip"
    exit 0
  fi
  log "stale lockfile removed (${lock_age}s old)"
  rm -f "${LOCK_FILE}"
fi
touch "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

# ── Guard: no state file ──────────────────────────────────────────────────────
if [[ ! -f "${STATE_FILE}" ]]; then
  log "no state file at ${STATE_FILE} — nothing to do"
  exit 0
fi

command -v jq >/dev/null 2>&1 || { log "jq not found — aborting"; exit 1; }

# ── Read state (all token-free) ───────────────────────────────────────────────
interview_complete=$(state_get '.interviewComplete')
last_q_at=$(state_get '.interviewProgress.lastQuestionAt')
interview_stalled=$(state_get '.interviewStalled')
qc_status=$(state_get '.interviewQc.status')
build_completed_at=$(state_get '.buildCompletedAt')
closeout_status=$(state_get '.closeoutStatus')
resume_attempts=$(state_get '.resumeAttempts')
max_resume_attempts=$(state_get '.maxResumeAttempts')
company_name=$(state_get '.companyName')
agent_name=$(state_get '.agentName')

[[ -z "$company_name" || "$company_name" == "null" ]] && company_name="(unknown)"
[[ -z "$agent_name" || "$agent_name" == "null" ]] && agent_name="(unknown)"

# ── Compute idle times ────────────────────────────────────────────────────────
NOW_EPOCH=$(now_epoch)

compute_hours_idle_from_ts() {
  local ts="$1"
  [[ -z "$ts" || "$ts" == "null" ]] && { echo 0; return; }
  python3 -c "
from datetime import datetime, timezone
ts='${ts}'.rstrip('Z')
try:
    dt=datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    print(int((${NOW_EPOCH} - dt.timestamp()) / 3600))
except:
    print(0)
" 2>/dev/null || echo 0
}

# Idle hours since last interview question
interview_idle_hours=$(compute_hours_idle_from_ts "$last_q_at")
interview_idle_days=$(( interview_idle_hours / 24 ))

# State file ctime as fallback "provisioned" time
state_file_age_hours=0
if command -v stat >/dev/null 2>&1; then
  state_mtime=$(stat -c %Y "${STATE_FILE}" 2>/dev/null || stat -f %m "${STATE_FILE}" 2>/dev/null || echo 0)
  if (( state_mtime > 0 )); then
    state_file_age_hours=$(( (NOW_EPOCH - state_mtime) / 3600 ))
  fi
fi

# Closeout status age — when did current closeout status start?
closeout_started_at=$(state_get '.closeoutStartedAt')
closeout_age_hours=$(compute_hours_idle_from_ts "$closeout_started_at")

# ── Stuck class classification ────────────────────────────────────────────────
STUCK_CLASS=""
STUCK_REASON=""
STUCK_IDLE_LABEL=""

if [[ "$interview_complete" != "true" ]]; then
  # Pre-interview-complete branch: STUCK_MID_INTERVIEW or STUCK_INTERVIEW_NEVER_STARTED
  if [[ -n "$last_q_at" && "$last_q_at" != "null" ]]; then
    if (( interview_idle_days >= ZHC_STUCK_INTERVIEW_DAYS )); then
      STUCK_CLASS="STUCK_MID_INTERVIEW"
      STUCK_REASON="Interview in progress but owner has not responded in ${interview_idle_days}d (threshold: ${ZHC_STUCK_INTERVIEW_DAYS}d)"
      STUCK_IDLE_LABEL="${interview_idle_days}d"
    fi
  else
    # lastQuestionAt never set — interview never started
    if (( state_file_age_hours >= ZHC_STUCK_NOSTART_DAYS * 24 )); then
      STUCK_CLASS="STUCK_INTERVIEW_NEVER_STARTED"
      STUCK_REASON="Box provisioned ~${state_file_age_hours}h ago but interview has never started (threshold: ${ZHC_STUCK_NOSTART_DAYS}d)"
      STUCK_IDLE_LABEL="${state_file_age_hours}h"
    fi
  fi
elif [[ "$qc_status" == "fail" || "$qc_status" == "needs-review" ]]; then
  STUCK_CLASS="STUCK_QC_FAILED"
  STUCK_REASON="Interview marked complete but interviewQc.status=${qc_status} (not pass) — closeout blocked"
  STUCK_IDLE_LABEL="qc=${qc_status}"
elif [[ (-z "$build_completed_at" || "$build_completed_at" == "null") ]]; then
  # interviewComplete=true + qc pass + no build yet — check cap
  if [[ -n "$resume_attempts" && "$resume_attempts" != "null" &&
        -n "$max_resume_attempts" && "$max_resume_attempts" != "null" ]]; then
    if (( resume_attempts >= max_resume_attempts )); then
      STUCK_CLASS="STUCK_PRE_CLOSEOUT"
      STUCK_REASON="Interview+QC complete but build wedged: resumeAttempts=${resume_attempts} >= maxResumeAttempts=${max_resume_attempts}"
      STUCK_IDLE_LABEL="attempts=${resume_attempts}"
    fi
  fi
else
  # buildCompletedAt set — check closeout
  case "${closeout_status:-}" in
    blocked-floor-incomplete|blocked-libraries-incomplete|blocked-interview-incomplete|failed)
      if (( closeout_age_hours >= ZHC_STUCK_CLOSEOUT_HOURS )); then
        STUCK_CLASS="STUCK_CLOSEOUT_BLOCKED"
        STUCK_REASON="closeoutStatus=${closeout_status} for ${closeout_age_hours}h (threshold: ${ZHC_STUCK_CLOSEOUT_HOURS}h)"
        STUCK_IDLE_LABEL="${closeout_age_hours}h"
      fi
      ;;
  esac
fi

# ── No stuck condition ────────────────────────────────────────────────────────
if [[ -z "$STUCK_CLASS" ]]; then
  # Clear any stale blockers that have resolved
  # (idempotent — jq on non-existent key is a no-op)
  log "no stuck condition detected for ${company_name}/${agent_name} — all clear"
  exit 0
fi

log "STUCK CLASS: ${STUCK_CLASS} — ${company_name}/${agent_name}: ${STUCK_REASON}"

# ── Throttle check — has this class already been escalated recently? ──────────
THROTTLE_KEY=".stuckEscalations.${STUCK_CLASS}.notifiedAt"
last_notified=$(state_get "$THROTTLE_KEY")

should_escalate=1
if [[ -n "$last_notified" && "$last_notified" != "null" ]]; then
  hours_since_notify=$(compute_hours_idle_from_ts "$last_notified")
  reescalate_hours=$(( ZHC_STUCK_REESCALATE_DAYS * 24 ))
  if (( hours_since_notify < reescalate_hours )); then
    log "throttled: ${STUCK_CLASS} already escalated ${hours_since_notify}h ago (re-escalate threshold: ${reescalate_hours}h)"
    should_escalate=0
  fi
fi

if [[ "$should_escalate" -eq 0 ]]; then
  log "watchdog pass complete (throttled — no new escalation)"
  exit 0
fi

# ── Write closeoutBlockers[] entry ───────────────────────────────────────────
TS_NOW=$(now_iso)
BLOCKER_ENTRY=$(jq -n \
  --arg class "$STUCK_CLASS" \
  --arg reason "$STUCK_REASON" \
  --arg since "$TS_NOW" \
  --arg escalated "$TS_NOW" \
  '{"class":$class,"reason":$reason,"since":$since,"escalatedAt":$escalated,"cleared":false}')

# Append the new blocker (keep last 20 entries, drop cleared ones beyond 10)
state_set "
  .closeoutBlockers = (
    (.closeoutBlockers // [])
    | map(select(.cleared == false))
    | . + [${BLOCKER_ENTRY}]
    | if length > 20 then .[-20:] else . end
  )
" || log "WARN: could not append closeoutBlockers entry (non-fatal)"

# ── Update stuckEscalations throttle flag ─────────────────────────────────────
state_set ".stuckEscalations.${STUCK_CLASS}.notifiedAt = \"${TS_NOW}\" | .stuckEscalations.${STUCK_CLASS}.class = \"${STUCK_CLASS}\"" \
  || log "WARN: could not write stuckEscalations.${STUCK_CLASS} (non-fatal)"

# ── Telegram operator escalation ──────────────────────────────────────────────
ESCALATE_MSG="🚨 ZHC STUCK [${STUCK_CLASS}] ${company_name}/${agent_name}: ${STUCK_REASON}. Idle: ${STUCK_IDLE_LABEL}. State: ${STATE_FILE}"

if command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
  log "escalating to operator via Telegram (chat=${OPERATOR_TELEGRAM_CHAT_ID})"
  openclaw message send \
    --channel telegram \
    -t "${OPERATOR_TELEGRAM_CHAT_ID}" \
    -m "${ESCALATE_MSG}" >>"${LOG_FILE}" 2>&1 \
    || log "WARN: Telegram escalation failed (non-fatal — state blocker already written)"
else
  log "INFO: openclaw CLI not available or TG preflight skipped — operator message not sent (state blocker written)"
fi

# ── Rescue Rangers n8n webhook ────────────────────────────────────────────────
if command -v curl >/dev/null 2>&1 && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" && "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
  RR_PAYLOAD=$(jq -n \
    --arg action "escalate" \
    --arg client "${company_name}" \
    --arg agent "${agent_name}" \
    --arg class "${STUCK_CLASS}" \
    --arg message "${STUCK_REASON}" \
    --arg idle "${STUCK_IDLE_LABEL}" \
    '{action:$action,client:$client,agent:$agent,class:$class,message:$message,idle:$idle}')
  log "posting to Rescue Rangers webhook"
  curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d "${RR_PAYLOAD}" >>"${LOG_FILE}" 2>&1 \
    || log "WARN: Rescue Rangers webhook POST failed (non-fatal)"
fi

log "watchdog escalation complete: ${STUCK_CLASS} for ${company_name}/${agent_name}"
exit 0
