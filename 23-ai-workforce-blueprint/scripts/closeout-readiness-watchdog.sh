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
#   STUCK_QC_FAILED            - interviewComplete but interviewQc.status == fail
#                                (v21.x: needs-review is BUILD-ELIGIBLE and no longer classed
#                                stuck here - it used to sit in this class forever and mask
#                                every build-progress class below it)
#   STUCK_PRE_CLOSEOUT         - QC build-eligible, buildCompletedAt=null, AND EITHER
#                                resumeAttempts >= maxResumeAttempts, OR the build was never
#                                kicked off (no/all-pending departments + 0 resumeAttempts),
#                                OR the build stalled part-way with no forward progress
#                                for >= ZHC_STUCK_CLOSEOUT_HOURS
#   STUCK_BUILD_GATES_INCOMPLETE - v21.x, THE CLOSED BLIND SPOT: every department is done but
#                                a completion gate never closed (roleLibraryStatus /
#                                sopLibraryStatus != done, or commsAutomationStatus
#                                non-terminal) and buildCompletedAt is still unset, with no
#                                forward progress for >= ZHC_STUCK_CLOSEOUT_HOURS. Such a box
#                                previously matched NO class at all - the watchdog logged
#                                "all clear" every 6h through a multi-day silent stall.
#   STUCK_CLOSEOUT_BLOCKED     - closeoutStatus in blocked-* | failed >= ZHC_STUCK_CLOSEOUT_HOURS
#
# PLUS one INDEPENDENT finding, escalated separately so it can neither mask nor be
# masked by the mutually-exclusive classes above (it is about the machinery, not the client):
#   STUCK_RECOVERY_LANE_MISSING - the build is unfinished but the workforce-build-resume cron
#                                is absent (self-removed / never registered) or the box is
#                                PARKED. That cron is the ONLY autonomous-recovery layer in
#                                this pipeline. When it is merely absent the watchdog SELF-HEALS
#                                by running scripts/ensure-pipeline-crons.sh (which stays
#                                park- and tombstone-aware, so it will not resurrect a cron an
#                                operator deliberately stopped) and escalates either way.
#                                A PARKED box is escalated but NEVER auto-un-parked -
#                                un-parking is operator-only (scripts/unpark-build.sh).
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

# ── Platform detection — via the shared resolver (false-negative #3 fix) ──────
# A pre-set OC_ROOT override is still honored (this caller's own semantics);
# only the /data-else-HOME detection is centralized. Identical inline fallback
# if the shared file is absent. See shared-utils/resolve-oc-root.sh.
if [[ -z "${OC_ROOT:-}" ]]; then
  _OC_ROOT_RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../shared-utils/resolve-oc-root.sh"
  # shellcheck source=/dev/null
  [[ -f "$_OC_ROOT_RESOLVER" ]] && source "$_OC_ROOT_RESOLVER"
  if declare -F resolve_oc_root >/dev/null 2>&1; then
    if _oc_root_resolved="$(resolve_oc_root)"; then
      OC_ROOT="$_oc_root_resolved"
    else
      echo "[closeout-readiness-watchdog] no OpenClaw root found; aborting" >&2
      exit 0
    fi
  elif [[ -d /data/.openclaw ]]; then
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
#
# UNIFIED RESOLUTION (circular-alerting-dependency fix): this used to be a PURE
# process-environment read with NO config-file/CLI resolution at all — dispatched
# by `openclaw cron` as a child of the running gateway, it only ever saw the
# environment the gateway had at ITS OWN start, so an `openclaw config set` was
# invisible here until the gateway restarted (the CLI's own message: "Restart
# the gateway to apply"). It also never checked OPERATOR_HELP_CHAT_ID, the
# back-compat key scripts/configure-operator-telegram.sh writes. Both defects
# are fixed by routing through the one shared resolver every other operator-
# alerting caller uses, so there is a single answer to "where does an operator
# alert go" — see shared-utils/operator-chat-id.sh for the full writeup
# (including how it now survives a dead gateway, the exact failure this
# watchdog exists to report).
_OC_OPERATOR_CHAT_RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/../../shared-utils/operator-chat-id.sh"
if [[ -f "$_OC_OPERATOR_CHAT_RESOLVER" ]]; then
  # shellcheck source=/dev/null
  source "$_OC_OPERATOR_CHAT_RESOLVER" 2>/dev/null || true
  OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_CHAT_ID:-}"
else
  # Fallback: the pre-fix inline chain (now also covering OPERATOR_HELP_CHAT_ID),
  # only reached if the shared resolver file is somehow absent from this checkout.
  OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-${OPERATOR_HELP_CHAT_ID:-}}}"
fi
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

# Read-side status-vocabulary normalizer. The contract word is "done"; agents write
# "complete". See the departments read below for the full rationale. Read-only by
# design — this watchdog observes, it never rewrites client state.
_norm_status() { case "${1:-}" in complete|completed) echo "done" ;; *) echo "${1:-}" ;; esac; }

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

# ── escalate_class CLASS REASON IDLE_LABEL ────────────────────────────────────
# The whole escalation body, factored out of the tail of this script so more than
# ONE condition can escalate in a single pass. The classification block below is
# deliberately mutually-exclusive top-down (one wedged CLIENT condition per pass),
# but the recovery-lane check added below is a different kind of finding — it is
# about the MACHINERY, not the client — and it must never mask, or be masked by, a
# client stuck class. Keeping it a function lets both escalate independently.
#
# Idempotent per class: throttled by stuckEscalations.<class>.notifiedAt, re-firing
# only after ZHC_STUCK_REESCALATE_DAYS. Returns 0 always (never aborts the pass).
escalate_class() {
  local _class="$1" _reason="$2" _idle="$3"
  local _last _hours_since _reescalate_hours _ts _msg _payload

  log "STUCK CLASS: ${_class} - ${company_name}/${agent_name}: ${_reason}"

  # ── Throttle check - has this class already been escalated recently? ────────
  _last=$(state_get ".stuckEscalations.${_class}.notifiedAt")
  if [[ -n "$_last" && "$_last" != "null" ]]; then
    _hours_since=$(compute_hours_idle_from_ts "$_last")
    _reescalate_hours=$(( ZHC_STUCK_REESCALATE_DAYS * 24 ))
    if (( _hours_since < _reescalate_hours )); then
      log "throttled: ${_class} already escalated ${_hours_since}h ago (re-escalate threshold: ${_reescalate_hours}h)"
      return 0
    fi
  fi

  # ── Write closeoutBlockers[] entry + stuckEscalations throttle flag ─────────
  # One atomic python write: append the new blocker (drop already-cleared entries,
  # keep the last 20) and stamp the stuckEscalations.<class> throttle flag.
  _ts=$(now_iso)
  state_append_blocker_and_throttle "$_class" "$_reason" "$_ts" \
    || log "WARN: could not append closeoutBlockers / stuckEscalations entry (non-fatal)"

  # ── Telegram operator escalation ───────────────────────────────────────────
  _msg="🚨 ZHC STUCK [${_class}] ${company_name}/${agent_name}: ${_reason}. Idle: ${_idle}. State: ${STATE_FILE}"
  if [[ -n "${OPERATOR_TELEGRAM_CHAT_ID}" ]] && command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
    log "escalating to operator via Telegram (chat=${OPERATOR_TELEGRAM_CHAT_ID})"
    openclaw message send \
      --channel telegram \
      -t "${OPERATOR_TELEGRAM_CHAT_ID}" \
      -m "${_msg}" >>"${LOG_FILE}" 2>&1 \
      || log "WARN: Telegram escalation failed (non-fatal - state blocker already written)"
  elif [[ -z "${OPERATOR_TELEGRAM_CHAT_ID}" ]]; then
    log "INFO: operator escalation chat not configured (OPERATOR_ESCALATION_CHAT_ID unset) - operator message skipped (state blocker written; Rescue Rangers still fires)"
  else
    log "INFO: openclaw CLI not available or TG preflight skipped - operator message not sent (state blocker written)"
  fi

  # ── Rescue Rangers n8n webhook ─────────────────────────────────────────────
  if command -v curl >/dev/null 2>&1 && [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" && "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
    _payload=$(_OC_RR_CLIENT="${company_name}" _OC_RR_AGENT="${agent_name}" \
      _OC_RR_CLASS="${_class}" _OC_RR_MSG="${_reason}" _OC_RR_IDLE="${_idle}" \
      python3 -c 'import json, os
print(json.dumps({"action": "escalate", "client": os.environ["_OC_RR_CLIENT"], "agent": os.environ["_OC_RR_AGENT"], "class": os.environ["_OC_RR_CLASS"], "message": os.environ["_OC_RR_MSG"], "idle": os.environ["_OC_RR_IDLE"]}))' 2>/dev/null)
    log "posting to Rescue Rangers webhook"
    curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
      -H "Content-Type: application/json" \
      ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} \
      -d "${_payload}" >>"${LOG_FILE}" 2>&1 \
      || log "WARN: Rescue Rangers webhook POST failed (non-fatal)"
  fi

  log "watchdog escalation complete: ${_class} for ${company_name}/${agent_name}"
  return 0
}

# ── Recovery-lane helpers (the machinery this watchdog now also watches) ───────
# resume-workforce-build.sh's own header: "This is the ONLY autonomous-recovery
# layer in the workforce-build pipeline. If this script doesn't run on a cron, an
# interrupted build will sit forever." Nothing was watching whether that cron still
# existed. It self-removes on several paths (a terminal state, the consecutive-stuck
# cap, the absolute ping ceiling) and un-parking is operator-only — so a box could
# end up with NO recovery lane at all, and nobody was ever told.
BOX_PARK_MARKER="${OC_ROOT}/workspace/.park/workforce-build.parked"

# 0 = present, 1 = definitively absent, 2 = cannot tell (no CLI / unparseable).
# "Cannot tell" must NEVER be reported as absent — a false "recovery layer missing"
# page every 6h would train operators to ignore this class.
_resume_cron_state() {
  command -v openclaw >/dev/null 2>&1 || return 2
  local raw
  raw=$(openclaw cron list --json 2>/dev/null) || return 2
  [[ -z "$raw" ]] && return 2
  printf '%s' "$raw" | python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception:
    sys.exit(2)
jobs = data if isinstance(data, list) else data.get('jobs', [])
if not isinstance(jobs, list):
    sys.exit(2)
sys.exit(0 if any((j or {}).get('name') == 'workforce-build-resume' for j in jobs) else 1)
" 2>/dev/null
  return $?
}

# Best-effort self-heal: re-run the shared cron registrar. It is idempotent, and it
# is already park-aware and tombstone-aware, so it will correctly REFUSE to
# resurrect a cron an operator deliberately parked or tombstoned.
_restore_resume_cron() {
  # Same candidate order scripts/unpark-build.sh uses, plus this checkout's own
  # repo-root path so the registrar is found in CI and in a git working tree too.
  local registrar
  for registrar in \
    "${OC_ROOT}/onboarding/scripts/ensure-pipeline-crons.sh" \
    "${OC_ROOT}/scripts/ensure-pipeline-crons.sh" \
    "${REPO_ROOT}/scripts/ensure-pipeline-crons.sh" \
    "${REPO_ROOT}/../scripts/ensure-pipeline-crons.sh"; do
    if [[ -f "$registrar" ]]; then
      log "recovery-lane: running ensure-pipeline-crons.sh to restore the workforce-build-resume cron ($registrar)"
      bash "$registrar" >>"${LOG_FILE}" 2>&1 || true
      return 0
    fi
  done
  log "recovery-lane: ensure-pipeline-crons.sh not found at any known path - cannot auto-restore"
  return 1
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
closeout_status="$(_norm_status "$(state_get '.closeoutStatus')")"
resume_attempts=$(state_get '.resumeAttempts')
max_resume_attempts=$(state_get '.maxResumeAttempts')
company_name=$(state_get '.companyName')
agent_name=$(state_get '.agentName')
# PRD-3.3 R3.4: signals for the fast "content complete but flag missing" class and
# for tightening STUCK_PRE_CLOSEOUT. dept_total/dept_pending let us detect a build
# that was never kicked off (no departments[] entries at all).
# phasesComplete length, departments length, and pending/failed departments count
# in ONE python pass (replaces three jq length/filter reads).
#
# VOCABULARY NORMALIZATION (read-side): the contract word is "done", but agents
# write "complete". A box was observed with every one of its departments at
# status:"complete", which made every `== "done"` counter read zero. The WRITE-side
# normalizer lives in resume-workforce-build.sh (one normalization point, run before
# any consumer reads the state); this watchdog additionally normalizes on READ so it
# reports the truth even on a box whose resume cron has not fired since - a watchdog
# must never be blinded by a synonym, and it must not mutate client state itself.
#
# Also emits dept_done and the last real forward-progress timestamp, which the
# build-gates stuck class below needs as its clock. State-file mtime is useless as a
# clock here: the resume cron rewrites resumeAttempts on every fire, so the file
# looks "fresh" for as long as the cron keeps making no progress.
_dept_counts=$(python3 - "${STATE_FILE}" <<'PY' 2>/dev/null
import json, sys

DONE = ('done', 'complete', 'completed')

try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
phases = (d.get('interviewProgress') or {}).get('phasesComplete') or []
depts = d.get('departments') or []
if not isinstance(phases, list): phases = []
if not isinstance(depts, list): depts = []
objs = [x for x in depts if isinstance(x, dict)]
pending = [x for x in objs if x.get('status') in ('pending', 'failed')]
done = [x for x in objs if x.get('status') in DONE]

# Last real forward motion: newest department completedAt, else the build/interview
# milestones. ISO-8601 strings sort lexicographically, so max() is correct here.
stamps = [x.get('completedAt') for x in objs]
stamps += [d.get('buildStartedAt'), d.get('interviewCompletedAt'),
           (d.get('interviewProgress') or {}).get('lastQuestionAt')]
stamps = [s for s in stamps if isinstance(s, str) and s.strip()]
last_progress = max(stamps) if stamps else ''

print(len(phases), len(depts), len(pending), len(done), last_progress or '-')
PY
)
read -r phases_complete_count dept_total dept_pending dept_done last_progress_at <<< "${_dept_counts:-0 0 0 0 -}"
: "${phases_complete_count:=0}" "${dept_total:=0}" "${dept_pending:=0}" "${dept_done:=0}" "${last_progress_at:=-}"
[[ "$last_progress_at" == "-" ]] && last_progress_at=""

# Build-completion gate fields (same read-side synonym tolerance as above).
role_library_status="$(_norm_status "$(state_get '.roleLibraryStatus')")"
sop_library_status="$(_norm_status "$(state_get '.sopLibraryStatus')")"
comms_automation_status="$(_norm_status "$(state_get '.commsAutomationStatus')")"

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

# Hours since the last REAL forward motion in the build (see the departments read
# above for how last_progress_at is chosen). Falls back to the interview clock when
# the build has produced no timestamps at all, so a never-started build still ages.
if [[ -n "$last_progress_at" ]]; then
  build_idle_hours=$(compute_hours_idle_from_ts "$last_progress_at")
else
  build_idle_hours="$interview_idle_hours"
fi
case "$build_idle_hours" in ''|*[!0-9]*) build_idle_hours=0 ;; esac

# gates_open: at least one build-completion gate is still non-terminal, so HOP-4
# (the buildCompletedAt writer in resume-workforce-build.sh) cannot fire. Mirrors
# that script's own library_dirty / comms_automation_dirty predicates exactly.
gates_open=0
[[ "$role_library_status" != "done" ]] && gates_open=1
[[ "$sop_library_status" != "done" ]] && gates_open=1
case "$comms_automation_status" in done|not-applicable) : ;; *) gates_open=1 ;; esac

# ── RECOVERY-LANE CHECK (runs BEFORE, and independently of, classification) ───
# STUCK_RECOVERY_LANE_MISSING. The build is not finished (we already exited above
# if the closeout is done|sent), so the workforce-build-resume cron MUST exist —
# it is the only thing that can advance this box without a human. If it is gone we
# try to restore it, and we escalate either way so the operator learns that the
# self-healing layer had failed. This is deliberately NOT one of the mutually-
# exclusive client stuck classes below: it is a finding about the machinery, and
# it must neither mask nor be masked by a client condition.
if [[ "$interview_complete" == "true" ]]; then
  if [[ -f "$BOX_PARK_MARKER" ]]; then
    # A parked box has NO recovery lane and un-parking is operator-only by
    # doctrine (scripts/unpark-build.sh). We never auto-un-park — we make the
    # dead end LOUD, which is what was missing.
    escalate_class "STUCK_RECOVERY_LANE_MISSING" \
      "The workforce build is PARKED (${BOX_PARK_MARKER}) while the closeout is still ${closeout_status:-unset}. A parked box has NO autonomous recovery lane: the resume cron is removed and will not be re-registered by any roll. Un-parking is operator-only - investigate, then run scripts/unpark-build.sh on the box." \
      "parked"
  else
    _resume_cron_state
    _rc_lane=$?
    if (( _rc_lane == 1 )); then
      _lane_reason="The workforce-build-resume cron is ABSENT while the build is unfinished (closeoutStatus=${closeout_status:-unset}, buildCompletedAt=${build_completed_at:-unset}). That cron is the ONLY autonomous-recovery layer in this pipeline - without it an interrupted build sits forever with no further attempts and no notification."
      if _restore_resume_cron; then
        _resume_cron_state
        if (( $? == 0 )); then
          _lane_reason="${_lane_reason} AUTO-HEALED: ensure-pipeline-crons.sh re-registered it on this pass. Investigate WHY it disappeared (a terminal-state self-removal, the consecutive-stuck cap, or the absolute ping ceiling)."
        else
          _lane_reason="${_lane_reason} AUTO-HEAL FAILED: ensure-pipeline-crons.sh ran but the cron is still not present. Manual intervention required on the box."
        fi
      else
        _lane_reason="${_lane_reason} AUTO-HEAL UNAVAILABLE: ensure-pipeline-crons.sh could not be located on this box. Manual intervention required."
      fi
      escalate_class "STUCK_RECOVERY_LANE_MISSING" "$_lane_reason" "cron-absent"
    elif (( _rc_lane == 2 )); then
      log "recovery-lane: could not determine whether the workforce-build-resume cron exists (no openclaw CLI or unparseable cron list) - NOT escalating on an unknown"
    else
      log "recovery-lane: workforce-build-resume cron present - autonomous recovery layer intact"
    fi
  fi
fi

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
elif [[ "$qc_status" == "fail" ]]; then
  # v21.x GATE-CONSISTENCY FIX: `needs-review` is no longer classified as stuck.
  # update-interview-state.sh's evidence gate has always treated qc rc=2
  # (needs-review) as "evidence supports completion", and the build lanes now agree
  # (kick + resume cron both accept pass|needs-review). Keeping needs-review here
  # would (a) contradict those lanes and (b) actively HARM: these classes are
  # mutually exclusive top-down, so a needs-review box would stop at STUCK_QC_FAILED
  # forever and could never reach the build-progress classes below - masking the
  # real reason it is wedged. Only `fail` is a genuine QC stop now.
  STUCK_CLASS="STUCK_QC_FAILED"
  STUCK_REASON="Interview marked complete but interviewQc.status=${qc_status} - closeout blocked"
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
  elif (( dept_total > 0 )) && (( build_idle_hours >= ZHC_STUCK_CLOSEOUT_HOURS )); then
    # ── v21.x THE BLIND SPOT, CLOSED ──────────────────────────────────────────
    # Everything above requires either an exhausted resume-attempt counter OR a
    # never-kicked build. A box with all departments DONE, a FAILED library, and
    # resumeAttempts=0 fell through EVERY class — so this watchdog logged
    # "no stuck condition detected ... all clear" every 6h for the entire
    # multi-day stall while the client heard nothing. The resume lane in that
    # state logs the SAME no-op line every 15 minutes (hundreds of identical
    # cycles); a recovery lane repeating itself hundreds of times without the
    # build advancing is definitionally stuck, and nothing was measuring it.
    #
    # The clock is build_idle_hours — time since the last REAL forward motion
    # (newest department completedAt, else buildStartedAt / interviewCompletedAt
    # / lastQuestionAt). State-file mtime would be useless: the resume cron
    # rewrites resumeAttempts on every fire, so the file always looks fresh.
    if (( dept_done == dept_total )) && (( gates_open == 1 )); then
      STUCK_CLASS="STUCK_BUILD_GATES_INCOMPLETE"
      STUCK_REASON="All ${dept_total} departments are done but the completion gates never closed and buildCompletedAt was never written: roleLibraryStatus=${role_library_status:-unset}, sopLibraryStatus=${sop_library_status:-unset}, commsAutomationStatus=${comms_automation_status:-unset}. No forward progress for ${build_idle_hours}h (threshold: ${ZHC_STUCK_CLOSEOUT_HOURS}h). The build cannot cross into the closeout while any gate is non-terminal - run scripts/verify-library-gate.sh on the box and check that the workforce-build-resume cron is still registered."
      STUCK_IDLE_LABEL="gates-open ${build_idle_hours}h"
    else
      STUCK_CLASS="STUCK_PRE_CLOSEOUT"
      STUCK_REASON="Build started but stalled part-way: ${dept_done}/${dept_total} departments done (${dept_pending} pending/failed), buildCompletedAt still unset, resumeAttempts=${_ra}/${_mra}. No forward progress for ${build_idle_hours}h (threshold: ${ZHC_STUCK_CLOSEOUT_HOURS}h) - the resume lane is firing without advancing, or is no longer registered."
      STUCK_IDLE_LABEL="stalled ${build_idle_hours}h"
    fi
  fi
else
  # buildCompletedAt set - check closeout
  case "${closeout_status:-}" in
    blocked-floor-incomplete|blocked-libraries-incomplete|blocked-interview-incomplete|blocked-qc-pending|failed)
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

escalate_class "$STUCK_CLASS" "$STUCK_REASON" "$STUCK_IDLE_LABEL"
exit 0
