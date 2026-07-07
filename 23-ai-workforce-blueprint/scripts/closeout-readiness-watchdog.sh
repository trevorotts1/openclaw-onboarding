#!/usr/bin/env bash
# closeout-readiness-watchdog.sh - PRD-2.15 operator escalation lane.
#
# A NEW cron (every 6h) that is the OPERATOR-FACING twin of the owner-facing
# interview-nudge cron. The nudge cron is, by binding design, an owner-only
# reminder. This watchdog is the operator escalation lane that was missing:
# it surfaces "client is one step from value and stuck" to the operator and
# Rescue Rangers, and acts as the first-class stuck-client surface.
#
# STUCK CLASSES (mutually exclusive, evaluated top-down):
#   STUCK_INTERVIEW_FLAG_MISSING  - interview CONTENT complete (qc=pass or all phases done)
#                                   but interviewComplete flag never written; FAST alert
#                                   (>= ZHC_STUCK_FLAG_MISSING_HOURS, default 6h) - the HOP-1 miss
#   STUCK_MID_INTERVIEW        - interview in progress, idle >= ZHC_STUCK_INTERVIEW_DAYS
#   STUCK_INTERVIEW_NEVER_STARTED - lastQuestionAt unset, box provisioned >= ZHC_STUCK_NOSTART_DAYS
#   STUCK_QC_FAILED            - interviewComplete but interviewQc.status in fail|needs-review
#   STUCK_PRE_CLOSEOUT         - QC passed, buildCompletedAt=null, AND EITHER resumeAttempts >=
#                                maxResumeAttempts OR the build was never kicked off (no/all-pending
#                                departments + 0 resumeAttempts) for >= ZHC_STUCK_CLOSEOUT_HOURS
#   STUCK_CLOSEOUT_BLOCKED     - closeoutStatus in blocked-* | failed >= ZHC_STUCK_CLOSEOUT_HOURS
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
# PRD-2.15 / v12.3.13
# SELF-REMOVAL MARKER (v12.3.13): watchdog removes itself when closeoutStatus is
# done|sent. Mirrors interview-nudge-cron.sh pattern. UUID written to
# .closeoutWatchdogCronUuid by ensure-pipeline-crons.sh _register_command_cron.
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
# PRD-3.3 R3.4 (auto-closeout): FAST class for "owner finished but the
# interviewComplete flag was never written." This is the exact HOP-1 miss
# (diag/03): the resume cron's recovery should catch it within a cron cycle, but
# if for any reason it does not, the operator must learn in HOURS - not after the
# 5-day STUCK_MID_INTERVIEW threshold, which wrongly assumes the owner went idle.
# Default 6h (one watchdog cycle plus margin).
ZHC_STUCK_FLAG_MISSING_HOURS="${ZHC_STUCK_FLAG_MISSING_HOURS:-6}"
# CO-MINGLING GUARD (v12.4.0): operator escalation destination is OPT-IN and
# CONFIGURABLE. NO hardcoded personal chat. Empty => the Telegram escalation
# below is SKIPPED (the state blocker is still written; Rescue Rangers still fires).
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}"
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

# ── JSON helpers (python3-backed) ─────────────────────────────────────────────
# Read/write build-state with python3 (guaranteed present in the OpenClaw
# container) instead of jq. jq is NOT shipped in the container image and vanished
# on a container recreate, which used to make this watchdog hard-abort ("jq not
# found - aborting") every cycle — silently killing the operator escalation lane.
# Parsing with python3 means a missing system binary can never break this lane.
# (fix/jq-hard-dep — remove hard jq dependency from the nudge + watchdog crons.)
state_get() {
  # $1 = simple dotted JSON path, e.g. .interviewProgress.lastQuestionAt or
  # .stuckEscalations.STUCK_MID_INTERVIEW.notifiedAt. Prints the value
  # ("true"/"false" for booleans, compact JSON for objects/arrays) or nothing
  # when the path is missing/null — mirrors jq '<path> // empty'.
  _OC_JSON_PATH="$1" python3 - "${STATE_FILE}" <<'PY' 2>/dev/null
import json, os, sys
path = os.environ.get('_OC_JSON_PATH', '').lstrip('.')
try:
    cur = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for key in [p for p in path.split('.') if p != '']:
    if isinstance(cur, dict) and key in cur:
        cur = cur[key]
    else:
        sys.exit(0)
# Mirror jq's `<path> // empty`: null AND boolean false both yield empty output.
if cur is None or cur is False:
    sys.exit(0)
if cur is True:
    sys.stdout.write('true')
elif isinstance(cur, (dict, list)):
    sys.stdout.write(json.dumps(cur))
else:
    sys.stdout.write(str(cur))
PY
}

# Set a single top-level build-state key to JSON null (replaces jq
# '.<key> = null'). $1 = bare key name (no leading dot). Best-effort.
state_set_null() {
  _OC_JSON_KEY="$1" python3 - "${STATE_FILE}" <<'PY' 2>/dev/null || return 1
import json, os, sys
f = sys.argv[1]; key = os.environ.get('_OC_JSON_KEY', '')
try:
    d = json.load(open(f))
except Exception:
    sys.exit(1)
d[key] = None
tmp = f + '.tmp'
with open(tmp, 'w') as fh:
    json.dump(d, fh, indent=2)
os.replace(tmp, f)
PY
}

# Append a closeoutBlockers[] entry (drop already-cleared entries, keep the last
# 20) AND stamp the stuckEscalations.<class> throttle flag in ONE atomic write.
# Replaces the two jq state_set programs + the `jq -n` BLOCKER_ENTRY construct.
#   $1 = stuck class  $2 = reason  $3 = ISO timestamp
state_append_blocker_and_throttle() {
  _OC_BLK_CLASS="$1" _OC_BLK_REASON="$2" _OC_BLK_TS="$3" \
  python3 - "${STATE_FILE}" <<'PY' 2>/dev/null || return 1
import json, os, sys
f = sys.argv[1]
cls = os.environ['_OC_BLK_CLASS']; reason = os.environ['_OC_BLK_REASON']; ts = os.environ['_OC_BLK_TS']
try:
    d = json.load(open(f))
except Exception:
    sys.exit(1)
# closeoutBlockers: keep only not-yet-cleared entries, append the new one, cap at 20.
blk = d.get('closeoutBlockers')
blk = [x for x in blk if isinstance(x, dict) and x.get('cleared') is False] if isinstance(blk, list) else []
blk.append({"class": cls, "reason": reason, "since": ts, "escalatedAt": ts, "cleared": False})
if len(blk) > 20:
    blk = blk[-20:]
d['closeoutBlockers'] = blk
# stuckEscalations.<class>: throttle flag (notifiedAt + class).
se = d.get('stuckEscalations')
if not isinstance(se, dict):
    se = {}
node = se.get(cls)
if not isinstance(node, dict):
    node = {}
node['notifiedAt'] = ts
node['class'] = cls
se[cls] = node
d['stuckEscalations'] = se
tmp = f + '.tmp'
with open(tmp, 'w') as fh:
    json.dump(d, fh, indent=2)
os.replace(tmp, f)
PY
}

now_iso() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

now_epoch() {
  date -u +%s
}

# ── Self-removal helpers ──────────────────────────────────────────────────────
# Resolve the registered cron UUID for this watchdog. Reads .closeoutWatchdogCronUuid
# from build-state first (fastest); falls back to a name-scan via `openclaw cron list
# --json` if the state field is absent (e.g. box installed before v12.3.13).
find_watchdog_cron_uuid() {
  local uuid
  uuid=$(state_get '.closeoutWatchdogCronUuid')
  if [[ -n "$uuid" && "$uuid" != "null" ]]; then
    echo "$uuid"
    return
  fi
  # Fallback: name-scan via openclaw cron list --json
  command -v openclaw >/dev/null 2>&1 || { echo ""; return; }
  local raw
  raw=$(openclaw cron list --json 2>/dev/null) || raw=""
  [[ -z "$raw" ]] && { echo ""; return; }
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$raw" | python3 -c "
import json,sys
try:
  data=json.loads(sys.stdin.read())
  jobs=data if isinstance(data,list) else data.get('jobs',[])
  m=[j for j in jobs if j.get('name')=='closeout-readiness-watchdog']
  print(m[0].get('id','') if m else '')
except:
  print('')
" 2>/dev/null || echo ""
  elif command -v jq >/dev/null 2>&1; then
    printf '%s' "$raw" | jq -r \
      '(if type=="array" then . else .jobs//[] end)|map(select(.name=="closeout-readiness-watchdog"))|.[0].id//empty' \
      2>/dev/null || echo ""
  else
    echo ""
  fi
}

# Remove this watchdog cron from the gateway cron store. Clears the UUID field
# in build-state so repeated `openclaw update` runs skip the rm. Non-fatal.
self_remove_cron_watchdog() {
  local reason="${1:-lifecycle-complete}"
  local uuid
  uuid=$(find_watchdog_cron_uuid)
  if [[ -n "$uuid" && "$uuid" != "null" ]]; then
    log "self-removing watchdog cron (uuid=${uuid}, reason=${reason})"
    if command -v openclaw >/dev/null 2>&1; then
      openclaw cron rm "$uuid" >/dev/null 2>&1 \
        && log "watchdog cron removed (uuid=${uuid})" \
        || log "WARN: openclaw cron rm ${uuid} rc!=0 (non-fatal; cron may already be removed or will self-expire)"
    fi
    # Clear UUID from build-state so ensure-pipeline-crons does not re-attempt rm
    state_set_null "closeoutWatchdogCronUuid" 2>/dev/null || true
  else
    log "self-remove: no watchdog UUID in state or cron list (already removed or never registered)"
  fi
}

# ── Lockfile ─────────────────────────────────────────────────────────────────
if [[ -f "${LOCK_FILE}" ]]; then
  lock_age=$(( $(now_epoch) - $(date -u -r "${LOCK_FILE}" +%s 2>/dev/null || now_epoch) ))
  if (( lock_age < STALE_LOCK_MINUTES * 60 )); then
    log "lockfile held (${lock_age}s old, limit=${STALE_LOCK_MINUTES}m) - already running; skip"
    exit 0
  fi
  log "stale lockfile removed (${lock_age}s old)"
  rm -f "${LOCK_FILE}"
fi
touch "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

# ── Guard: no state file ──────────────────────────────────────────────────────
if [[ ! -f "${STATE_FILE}" ]]; then
  log "no state file at ${STATE_FILE} - nothing to do"
  exit 0
fi

# python3 is the JSON parser now (guaranteed present in the container). If it is
# somehow absent, degrade to a graceful no-op (exit 0) rather than a hard abort —
# a missing binary must never mark this maintenance cron as failed.
command -v python3 >/dev/null 2>&1 || { log "python3 not found - skipping (cannot parse state)"; exit 0; }

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
# PRD-3.3 R3.4: signals for the fast "content complete but flag missing" class and
# for tightening STUCK_PRE_CLOSEOUT. dept_total/dept_pending let us detect a build
# that was never kicked off (no departments[] entries at all).
# phasesComplete length, departments length, and pending/failed departments count
# in ONE python pass (replaces three jq length/filter reads).
_dept_counts=$(python3 - "${STATE_FILE}" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
phases = (d.get('interviewProgress') or {}).get('phasesComplete') or []
depts = d.get('departments') or []
if not isinstance(phases, list): phases = []
if not isinstance(depts, list): depts = []
pending = [x for x in depts if isinstance(x, dict) and x.get('status') in ('pending', 'failed')]
print(len(phases), len(depts), len(pending))
PY
)
read -r phases_complete_count dept_total dept_pending <<< "${_dept_counts:-0 0 0}"
: "${phases_complete_count:=0}" "${dept_total:=0}" "${dept_pending:=0}"

[[ -z "$company_name" || "$company_name" == "null" ]] && company_name="(unknown)"
[[ -z "$agent_name" || "$agent_name" == "null" ]] && agent_name="(unknown)"

# ── Lifecycle complete: self-remove and exit ──────────────────────────────────
# Token-free check (closeoutStatus already read above). When the closeout is
# done or sent this watchdog has no remaining purpose. Remove the cron from the
# registry immediately and exit. This is the PRIMARY self-removal path that
# ensures the cron does NOT linger on completed boxes. (The sweep in
# ensure-pipeline-crons.sh is the fleet-convergence backstop that fires
# proactively on every `openclaw update` run before the cron can self-fire.)
if [[ "${closeout_status}" == "done" || "${closeout_status}" == "sent" ]]; then
  log "closeoutStatus=${closeout_status} — closeout complete; self-removing watchdog cron"
  self_remove_cron_watchdog "closeout-${closeout_status}"
  exit 0
fi

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

# Closeout status age - when did current closeout status start?
closeout_started_at=$(state_get '.closeoutStartedAt')
closeout_age_hours=$(compute_hours_idle_from_ts "$closeout_started_at")

# ── Stuck class classification ────────────────────────────────────────────────
STUCK_CLASS=""
STUCK_REASON=""
STUCK_IDLE_LABEL=""

if [[ "$interview_complete" != "true" ]]; then
  # Pre-interview-complete branch:
  #   STUCK_INTERVIEW_FLAG_MISSING (FAST) - content looks complete, flag missing
  #   STUCK_MID_INTERVIEW                 - interview genuinely idle (owner stopped)
  #   STUCK_INTERVIEW_NEVER_STARTED       - interview never began
  if [[ -n "$last_q_at" && "$last_q_at" != "null" ]]; then
    # PRD-3.3 R3.4 (auto-closeout): FAST class first. If the interview CONTENT
    # looks complete (QC already returned 'pass' against the transcript, OR every
    # interview phase is marked complete) but interviewComplete was never written,
    # this is the HOP-1 miss (owner finished, agent never flagged it). Alert the
    # operator in HOURS, not the 5-day idle threshold - the owner did NOT go idle,
    # the flag write was simply dropped. This must NOT be mistaken for STUCK_MID_
    # INTERVIEW (which assumes the owner went silent). Re-running the resume cron
    # auto-recovers this (R3.2); the watchdog is the visibility backstop.
    _content_complete=0
    if [[ "$qc_status" == "pass" ]]; then
      _content_complete=1
    elif (( phases_complete_count >= 6 )); then
      # All Phase 1-6 arcs marked complete in interviewProgress.phasesComplete.
      _content_complete=1
    fi
    if (( _content_complete == 1 )) && (( interview_idle_hours >= ZHC_STUCK_FLAG_MISSING_HOURS )); then
      STUCK_CLASS="STUCK_INTERVIEW_FLAG_MISSING"
      STUCK_REASON="Interview CONTENT looks complete (qc=${qc_status:-none}, phasesComplete=${phases_complete_count}) but interviewComplete flag was never written - owner finished but the build never started (HOP-1 miss). Idle ${interview_idle_hours}h (threshold: ${ZHC_STUCK_FLAG_MISSING_HOURS}h). The resume cron should auto-recover; if this persists, run update-interview-state.sh --complete on the box."
      STUCK_IDLE_LABEL="${interview_idle_hours}h"
    elif (( interview_idle_days >= ZHC_STUCK_INTERVIEW_DAYS )); then
      STUCK_CLASS="STUCK_MID_INTERVIEW"
      STUCK_REASON="Interview in progress but owner has not responded in ${interview_idle_days}d (threshold: ${ZHC_STUCK_INTERVIEW_DAYS}d)"
      STUCK_IDLE_LABEL="${interview_idle_days}d"
    fi
  else
    # lastQuestionAt never set - interview never started
    if (( state_file_age_hours >= ZHC_STUCK_NOSTART_DAYS * 24 )); then
      STUCK_CLASS="STUCK_INTERVIEW_NEVER_STARTED"
      STUCK_REASON="Box provisioned ~${state_file_age_hours}h ago but interview has never started (threshold: ${ZHC_STUCK_NOSTART_DAYS}d)"
      STUCK_IDLE_LABEL="${state_file_age_hours}h"
    fi
  fi
elif [[ "$qc_status" == "fail" || "$qc_status" == "needs-review" ]]; then
  STUCK_CLASS="STUCK_QC_FAILED"
  STUCK_REASON="Interview marked complete but interviewQc.status=${qc_status} (not pass) - closeout blocked"
  STUCK_IDLE_LABEL="qc=${qc_status}"
elif [[ (-z "$build_completed_at" || "$build_completed_at" == "null") ]]; then
  # interviewComplete=true + qc pass + no build yet - STUCK_PRE_CLOSEOUT.
  # Two ways to be wedged here:
  #  (a) the build kicked off and exhausted resume attempts (resumeAttempts cap), OR
  #  (b) PRD-3.3 R3.4: the build was NEVER kicked off - departments[] is empty (or
  #      every dept is still pending) AND resumeAttempts is 0/unset. The OLD cap
  #      check could never fire for this case because the counter only advances when
  #      the resume cron dispatches, and a never-kicked build sits at 0 forever.
  #      We now also trip when the build has been "complete interview, empty/all-
  #      pending departments, zero progress" for >= the closeout-hours threshold,
  #      measured from the last interview activity. This catches the exact silent-
  #      strand the auto-kick (R3.1) is meant to prevent, as a backstop.
  _ra="${resume_attempts}"; [[ -z "$_ra" || "$_ra" == "null" ]] && _ra=0
  _mra="${max_resume_attempts}"; [[ -z "$_mra" || "$_mra" == "null" ]] && _mra=12
  if (( _ra >= _mra )); then
    STUCK_CLASS="STUCK_PRE_CLOSEOUT"
    STUCK_REASON="Interview+QC complete but build wedged: resumeAttempts=${_ra} >= maxResumeAttempts=${_mra}"
    STUCK_IDLE_LABEL="attempts=${_ra}"
  elif (( dept_total == 0 || dept_pending == dept_total )) && (( _ra == 0 )) \
       && (( interview_idle_hours >= ZHC_STUCK_CLOSEOUT_HOURS )); then
    STUCK_CLASS="STUCK_PRE_CLOSEOUT"
    STUCK_REASON="Interview+QC complete but the build was NEVER kicked off (departments=${dept_total}, all pending=${dept_pending}, resumeAttempts=0) for ${interview_idle_hours}h (threshold: ${ZHC_STUCK_CLOSEOUT_HOURS}h). The auto-kick / resume cron did not start the build - investigate the box."
    STUCK_IDLE_LABEL="never-kicked ${interview_idle_hours}h"
  fi
else
  # buildCompletedAt set - check closeout
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
  # Nothing wedged: no blocker is written and no throttle flag is stamped.
  log "no stuck condition detected for ${company_name}/${agent_name} - all clear"
  exit 0
fi

log "STUCK CLASS: ${STUCK_CLASS} - ${company_name}/${agent_name}: ${STUCK_REASON}"

# ── Throttle check - has this class already been escalated recently? ──────────
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
  log "watchdog pass complete (throttled - no new escalation)"
  exit 0
fi

# ── Write closeoutBlockers[] entry + stuckEscalations throttle flag ───────────
# One atomic python write: append the new blocker (drop already-cleared entries,
# keep the last 20) and stamp the stuckEscalations.<class> throttle flag.
TS_NOW=$(now_iso)
state_append_blocker_and_throttle "$STUCK_CLASS" "$STUCK_REASON" "$TS_NOW" \
  || log "WARN: could not append closeoutBlockers / stuckEscalations entry (non-fatal)"

# ── Telegram operator escalation ──────────────────────────────────────────────
ESCALATE_MSG="🚨 ZHC STUCK [${STUCK_CLASS}] ${company_name}/${agent_name}: ${STUCK_REASON}. Idle: ${STUCK_IDLE_LABEL}. State: ${STATE_FILE}"

if [[ -n "${OPERATOR_TELEGRAM_CHAT_ID}" ]] && command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
  log "escalating to operator via Telegram (chat=${OPERATOR_TELEGRAM_CHAT_ID})"
  openclaw message send \
    --channel telegram \
    -t "${OPERATOR_TELEGRAM_CHAT_ID}" \
    -m "${ESCALATE_MSG}" >>"${LOG_FILE}" 2>&1 \
    || log "WARN: Telegram escalation failed (non-fatal - state blocker already written)"
elif [[ -z "${OPERATOR_TELEGRAM_CHAT_ID}" ]]; then
  log "INFO: operator escalation chat not configured (OPERATOR_ESCALATION_CHAT_ID unset) - operator message skipped (state blocker written; Rescue Rangers still fires)"
else
  log "INFO: openclaw CLI not available or TG preflight skipped - operator message not sent (state blocker written)"
fi

# ── Rescue Rangers n8n webhook ────────────────────────────────────────────────
if command -v curl >/dev/null 2>&1 && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" && "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
  RR_PAYLOAD=$(_OC_RR_CLIENT="${company_name}" _OC_RR_AGENT="${agent_name}" \
    _OC_RR_CLASS="${STUCK_CLASS}" _OC_RR_MSG="${STUCK_REASON}" _OC_RR_IDLE="${STUCK_IDLE_LABEL}" \
    python3 -c 'import json, os
print(json.dumps({"action": "escalate", "client": os.environ["_OC_RR_CLIENT"], "agent": os.environ["_OC_RR_AGENT"], "class": os.environ["_OC_RR_CLASS"], "message": os.environ["_OC_RR_MSG"], "idle": os.environ["_OC_RR_IDLE"]}))' 2>/dev/null)
  log "posting to Rescue Rangers webhook"
  curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} \
    -d "${RR_PAYLOAD}" >>"${LOG_FILE}" 2>&1 \
    || log "WARN: Rescue Rangers webhook POST failed (non-fatal)"
fi

log "watchdog escalation complete: ${STUCK_CLASS} for ${company_name}/${agent_name}"
exit 0
