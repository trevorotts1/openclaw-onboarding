#!/usr/bin/env bash
# interview-nudge-cron.sh - PRD-2.15: State-driven, gateway-routed nudge cron
# for incomplete AI Workforce interviews.
#
# Registered every 6h by install.sh. Mirrors the cheap-check-first / kill-
# condition / lockfile / gateway-routed pattern from resume-closeout-cron.sh.
#
# LOOP DOCTRINE:
#   Cheap trigger check (token-free): reads .workforce-build-state.json.
#   Only invokes the Python worker (expensive) when idle threshold is reached
#   and the nudge has not already been sent.
#
# KILL CONDITIONS:
#   • interviewComplete == true → self-remove this cron + exit 0 (no nudge)
#     — this kill condition is UNCHANGED under AI Workforce standard-first
#     (2026-08-04): the prebuild is not interview progress and never silences
#     the nudge.
#   • No companies with a lastQuestionAt set → nothing to do (exit 0)
#     — under standard-first the prebuild writes NO lastQuestionAt, so a
#     prebuilt box whose owner never started the interview stays in this
#     not-started state until the first answer; the prebuild does not count
#     as interview progress (asserted by
#     tests/unit/standard-first-cron-awareness.test.sh).
#   • Under 24h idle → exit 0 (cheap check)
#
# GATEWAY RULE (BINDING - no exceptions):
#   All Telegram sends go through `openclaw message send`. NEVER use direct
#   direct Telegram Bot API calls. If the openclaw CLI is absent → log and skip
#   (do NOT fall back to direct HTTP).
#
# OPERATOR-ANNOUNCE RULE (BINDING - v12.3.10):
#   This cron is registered in COMMAND mode (no --channel/--to/--message).
#   Status lines (idle hours, "complete - exit", "no owner chat") are written to
#   $OC_ROOT/workspace/.interview-nudge.log ONLY. They are NEVER spoken into a
#   Telegram chat. The ONLY Telegram traffic is a real client-facing nudge,
#   routed to the CLIENT owner via shared-utils/nudge-incomplete-interviews.py
#   which enforces OPERATOR_CHAT_IDS rejection.
#
# SELF-REMOVAL (v12.3.10):
#   When interviewComplete=true, the shim removes the interview-nudge cron from
#   openclaw's registry (keyed on .interviewNudgeUuid, with a name-scan fallback)
#   and then exits 0. This guarantees no live nudge cron remains for a completed
#   client - even on boxes installed before run-closeout.sh's primary removal path.
#
# IDEMPOTENCY:
#   The Python worker (nudge-incomplete-interviews.py) records sent nudges
#   per company in the state file. The cron reads the state before calling
#   the worker, so it can skip a company that already got the current nudge.
#
# NO-FABRICATION RULE (binding):
#   Nudges are REMINDERS ONLY. This script never triggers Option B, never
#   writes answers, and never treats an unanswered nudge as consent.
#
# PRD-2.15 / v12.3.10
set -uo pipefail

# ─── Durable jq resolution (2026-08-17) ──────────────────────────────────────
# The OpenClaw container image does not ship jq, and a jq installed with the
# distro package manager VANISHES on container recreate — the documented
# failure that silently killed owner nudges (fix/jq-hard-dep) and, under
# `set -euo pipefail`, aborts this script outright with rc 127.
#
# ~/.openclaw is a persistent bind mount on container boxes, so a static jq
# kept at ~/.openclaw/bin/jq survives recreate. Prefer PATH's jq when present;
# otherwise fall back to the persistent copy. Prepending a PATH entry cannot
# change any filter's semantics, which is why this is done here rather than by
# hand-translating ~80 jq expressions.
if ! command -v jq >/dev/null 2>&1; then
  for _oc_jq_dir in "${HOME:-/root}/.openclaw/bin" /data/.openclaw/bin; do
    if [ -x "$_oc_jq_dir/jq" ]; then
      PATH="$_oc_jq_dir:$PATH"
      export PATH
      break
    fi
  done
  unset _oc_jq_dir
fi
# ─────────────────────────────────────────────────────────────────────────────


# ── Platform detection ───────────────────────────────────────────────────────
# Allow OC_ROOT to be overridden by the environment (used by test harnesses and
# fleet-rescue scenarios where the root differs from the standard paths).
if [[ -z "${OC_ROOT:-}" ]]; then
  if [[ -d /data/.openclaw ]]; then
    OC_ROOT=/data/.openclaw
  elif [[ -d "${HOME}/.openclaw" ]]; then
    OC_ROOT="${HOME}/.openclaw"
  else
    echo "[interview-nudge-cron] no OpenClaw root found; aborting" >&2
    exit 0
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

STATE_FILE="${OC_ROOT}/workspace/.workforce-build-state.json"
LOCK_FILE="${OC_ROOT}/workspace/.interview-nudge.lock"
LOG_FILE="${OC_ROOT}/workspace/.interview-nudge.log"
NUDGE_WORKER="${REPO_ROOT}/shared-utils/nudge-incomplete-interviews.py"
STALE_LOCK_MINUTES=15

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${LOG_FILE}"
}

# ── JSON helpers (python3-backed) ─────────────────────────────────────────────
# These read/write build-state with python3 (guaranteed present in the OpenClaw
# container) instead of jq. jq is NOT shipped in the container image and vanished
# on a container recreate, which used to make this cron hard-abort ("jq not found
# - aborting") every cycle — silently killing owner nudges. Parsing with python3
# means a missing system binary can never break this lane again.
# (fix/jq-hard-dep — remove hard jq dependency from the nudge + watchdog crons.)
state_get() {
  # $1 = simple dotted JSON path, e.g. .interviewProgress.lastQuestionAt
  # Prints the value ("true"/"false" for booleans, compact JSON for objects/arrays)
  # or nothing when the path is missing/null — mirrors jq '<path> // empty'.
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

# Clear the interview-nudge cron UUID from build-state after self-removal.
# Replaces the old jq 'del(.interviewNudgeUuid) | .interviewNudgeRegisteredAt = null'.
state_clear_nudge_uuid() {
  python3 - "${STATE_FILE}" <<'PY' 2>/dev/null || return 1
import json, os, sys
f = sys.argv[1]
try:
    d = json.load(open(f))
except Exception:
    sys.exit(1)
d.pop('interviewNudgeUuid', None)
d['interviewNudgeRegisteredAt'] = None
tmp = f + '.tmp'
with open(tmp, 'w') as fh:
    json.dump(d, fh, indent=2)
os.replace(tmp, f)
PY
}

# ── Self-removal (v12.3.10) ───────────────────────────────────────────────────
# Find the cron UUID from state (preferred) or by name-scan (fallback for
# boxes installed before UUID recording was added).
find_nudge_cron_uuid() {
  if [[ -f "${STATE_FILE}" ]] && command -v python3 >/dev/null 2>&1; then
    local uuid
    uuid=$(state_get '.interviewNudgeUuid')
    if [[ -n "$uuid" && "$uuid" != "null" ]]; then
      printf '%s' "$uuid"
      return 0
    fi
  fi
  # Fallback: scan openclaw cron list by name
  command -v openclaw >/dev/null 2>&1 || { printf ''; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/interview-nudge/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}

self_remove_cron() {
  local reason="${1:-interviewComplete}"
  local uuid
  uuid=$(find_nudge_cron_uuid)
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not find interview-nudge cron UUID - may already be removed"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if command -v openclaw >/dev/null 2>&1; then
    openclaw cron rm "$uuid" 2>>"${LOG_FILE}" || log "WARN: cron rm failed (tolerated)"
  fi
  # Clear UUID from build-state
  if [[ -f "${STATE_FILE}" ]]; then
    state_clear_nudge_uuid 2>/dev/null || true
  fi
  # Kill loop-registry entry if available
  local _REPO_ROOT
  _REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  if [[ -f "${_REPO_ROOT}/scripts/loop-registry.sh" ]]; then
    LOOP_REGISTRY_FILE="${OC_ROOT}/workspace/.loop-registry.json" \
    # shellcheck disable=SC1090
    source "${_REPO_ROOT}/scripts/loop-registry.sh" 2>/dev/null || true
    LOOP_REGISTRY_FILE="${OC_ROOT}/workspace/.loop-registry.json" \
    lr_kill "interview-nudge" 2>/dev/null || true
  fi
}

# ── Lockfile ─────────────────────────────────────────────────────────────────
if [[ -f "${LOCK_FILE}" ]]; then
  lock_age=$(( $(date -u +%s) - $(date -u -r "${LOCK_FILE}" +%s 2>/dev/null || date -u +%s) ))
  if (( lock_age < STALE_LOCK_MINUTES * 60 )); then
    log "lockfile held (${lock_age}s old, limit=${STALE_LOCK_MINUTES}m) - nudge worker may still be running; skip"
    exit 0
  fi
  log "stale lockfile removed (${lock_age}s old)"
  rm -f "${LOCK_FILE}"
fi
touch "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

# ── No state file ─────────────────────────────────────────────────────────────
if [[ ! -f "${STATE_FILE}" ]]; then
  log "no state file at ${STATE_FILE} - nothing to do"
  exit 0
fi

# python3 is the JSON parser now (guaranteed present in the container). If it is
# somehow absent, degrade to a graceful no-op (exit 0) rather than a hard abort —
# a missing binary must never mark this maintenance cron as failed.
command -v python3 >/dev/null 2>&1 || { log "python3 not found - skipping (cannot parse state)"; exit 0; }

# ── Cheap trigger check (token-free) ─────────────────────────────────────────
interview_complete=$(state_get '.interviewComplete')
last_q_at=$(state_get '.interviewProgress.lastQuestionAt')
# AI WORKFORCE STANDARD-FIRST (2026-08-04): read-only awareness of the
# prebuild state. The kill condition below stays interviewComplete == true;
# a standard prebuild is NOT interview progress and never silences this cron.
# These reads are the only standard-first coupling in this file.
build_type=$(state_get '.buildType')
prebuild_status=$(state_get '.standardPrebuild.status')
prebuild_ready_at=$(state_get '.standardPrebuild.standardReadyAt')

if [[ "${interview_complete}" == "true" ]]; then
  log "interviewComplete=true - interview done, no nudge needed; self-removing cron"
  self_remove_cron "interviewComplete"
  exit 0
fi

if [[ -z "${last_q_at}" ]]; then
  if [[ "${build_type}" == "standard-first" && "${prebuild_status}" == "done" ]]; then
    # Standard-first: the company's standard foundation is already prebuilt,
    # but the owner has not started the interview yet (the prebuild writes no
    # lastQuestionAt, so this state is exactly "prebuilt, interview not
    # started"). There is nothing to measure idle time against until the first
    # answer, so exit the same as the legacy not-started path - but log the
    # standard-first condition explicitly so the box is visible in the nudge
    # log. Once the owner answers one question, lastQuestionAt exists and this
    # box rejoins the normal nudge cadence below (with the standard-first
    # nudge copy exported to the worker).
    log "standard-first: standard foundation prebuilt (standardPrebuild.status=done) but interviewProgress.lastQuestionAt not set - owner has not started the interview; nothing to nudge against yet (prebuild does not count as interview progress); exit"
  else
    log "interviewProgress.lastQuestionAt not set - interview not started or state missing; exit"
  fi
  exit 0
fi

# ── AI WORKFORCE STANDARD-FIRST (2026-08-04): nudge copy ─────────────────────
# A standard-first box whose owner STARTED the interview then stalled is
# nudged with the SAME cadence as today (24h idle floor, same thresholds).
# The standard-first nudge copy ("Review your pre-built company" instead of
# "Finish your interview") is exported to the worker via WORKFORCE_NUDGE_COPY
# so the owner-facing text matches the review-the-built-set flow. The legacy
# box (buildType absent) exports the default copy and is otherwise untouched.
WORKFORCE_NUDGE_COPY="default"
export WORKFORCE_NUDGE_COPY
if [[ "${build_type}" == "standard-first" && "${prebuild_status}" == "done" ]]; then
  WORKFORCE_NUDGE_COPY="review-prebuilt-company"
  export WORKFORCE_NUDGE_COPY
  log "standard-first: exporting WORKFORCE_NUDGE_COPY=review-prebuilt-company (owner-facing copy: review your pre-built company, not 'finish your interview')"
fi

# ── PRD-3.3 R3.5 (auto-closeout): do NOT nudge an owner who already FINISHED ──
# The nudge cron used to key "needs nudge" purely off interviewComplete != true.
# That wrongly nudged an owner who finished the interview but whose interviewComplete
# flag was never written (the HOP-1 miss, diag/03) - telling them to "finish" the
# interview they already finished. Gate the OWNER nudge on a real "content
# incomplete" signal: if the QC gate already returned 'pass' against the transcript,
# OR every interview phase is marked complete, the CONTENT is done - the owner must
# NOT be nudged. Instead this is a flag-missing condition the resume cron recovers
# (R3.2) and the operator watchdog surfaces (R3.4 STUCK_INTERVIEW_FLAG_MISSING).
# Hand off to the watchdog (operator lane) and exit WITHOUT an owner nudge.
nudge_qc_status=$(state_get '.interviewQc.status')
nudge_phases_complete=$(python3 - "${STATE_FILE}" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    v = (d.get('interviewProgress') or {}).get('phasesComplete') or []
    print(len(v) if isinstance(v, list) else 0)
except Exception:
    print(0)
PY
)
nudge_phases_complete=${nudge_phases_complete:-0}
_content_complete_no_flag=0
if [[ "${nudge_qc_status}" == "pass" ]]; then
  _content_complete_no_flag=1
elif (( nudge_phases_complete >= 6 )); then
  _content_complete_no_flag=1
fi
if (( _content_complete_no_flag == 1 )); then
  log "interview CONTENT complete (qc=${nudge_qc_status:-none}, phasesComplete=${nudge_phases_complete}) but interviewComplete flag missing - NOT nudging the owner (they finished). Handing off to operator watchdog for the flag-missing condition."
  WATCHDOG_FM="${SCRIPT_DIR}/closeout-readiness-watchdog.sh"
  if [[ -f "$WATCHDOG_FM" ]]; then
    bash "$WATCHDOG_FM" --from-nudge >>"${LOG_FILE}" 2>&1 || log "WARN: watchdog invocation (flag-missing) returned non-zero (non-fatal)"
  else
    log "WARN: closeout-readiness-watchdog.sh not found at $WATCHDOG_FM - flag-missing not surfaced to operator"
  fi
  exit 0
fi

# ── Compute idle hours ────────────────────────────────────────────────────────
NOW_EPOCH=$(date -u +%s)
# Parse lastQuestionAt ISO timestamp to epoch
LAST_EPOCH=$(python3 -c "
from datetime import datetime, timezone
import sys
ts = '${last_q_at}'.rstrip('Z')
try:
    dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    print(int(dt.timestamp()))
except Exception as e:
    print(0)
" 2>/dev/null || echo 0)

# AI WORKFORCE STANDARD-FIRST (2026-08-04): if lastQuestionAt carries an
# implausibly old timestamp (a seeding/migration artifact: older than the
# prebuild ready-time, or older than 10 years), anchor the idle clock to
# standardReadyAt instead so the first nudge is measured from a real system
# event rather than firing immediately. Real interview answers are always
# NEWER than the prebuild, so this fallback can never move a genuine idle
# measurement. Legacy boxes (buildType absent / prebuild not done) skip it.
if [[ "${build_type}" == "standard-first" && "${prebuild_status}" == "done" \
      && -n "${prebuild_ready_at}" && "${prebuild_ready_at}" != "null" ]]; then
  if python3 -c "
from datetime import datetime, timezone
import sys

def epoch(ts):
    try:
        return int(datetime.fromisoformat(ts.rstrip('Z')).replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None

last_q = epoch('${last_q_at}')
ready = epoch('${prebuild_ready_at}')
if last_q is None or ready is None:
    sys.exit(1)
# Artifact: at/before the prebuild ready-time, or older than 10 years.
sys.exit(0 if (last_q <= ready or last_q <= ready - 315360000) else 1)
" 2>/dev/null; then
    LAST_Q_AT_ORIGINAL="${last_q_at}"
    last_q_at="${prebuild_ready_at}"
    LAST_EPOCH=$(python3 -c "
from datetime import datetime, timezone
ts = '${last_q_at}'.rstrip('Z')
try:
    dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    print(int(dt.timestamp()))
except Exception:
    print(0)
" 2>/dev/null || echo 0)
    log "standard-first: lastQuestionAt='${LAST_Q_AT_ORIGINAL}' is at or before the prebuild ready-time (seeding artifact) - anchoring the nudge idle clock to standardReadyAt=${prebuild_ready_at}"
  fi
fi

if [[ "${LAST_EPOCH}" -eq 0 ]]; then
  log "WARN: could not parse lastQuestionAt='${last_q_at}'; skipping"
  exit 0
fi

HOURS_IDLE=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))
log "interview idle for ${HOURS_IDLE}h (lastQuestionAt=${last_q_at})"

if (( HOURS_IDLE < 24 )); then
  log "idle < 24h - no nudge yet; exit"
  exit 0
fi

# ── Check if the applicable nudge was already sent ────────────────────────────
# The worker records nudges_sent in the state (or in the handoff file as fallback).
# We delegate the per-nudge dedup logic to the Python worker itself.

# ── Verify gateway CLI is available ──────────────────────────────────────────
if ! command -v openclaw >/dev/null 2>&1; then
  log "WARN: openclaw CLI not found - cannot send nudge via gateway; skip (no direct-HTTP fallback)"
  exit 0
fi

# ── Verify worker script exists ───────────────────────────────────────────────
if [[ ! -f "${NUDGE_WORKER}" ]]; then
  log "ERROR: nudge worker not found at ${NUDGE_WORKER}"
  exit 1
fi

# ── Invoke the Python worker ──────────────────────────────────────────────────
log "dispatching nudge worker (idle=${HOURS_IDLE}h)"
if python3 "${NUDGE_WORKER}" 2>>"${LOG_FILE}"; then
  log "nudge worker completed successfully"
else
  rc=$?
  log "nudge worker exited with rc=$rc"
fi

# ── PRD-2.15 (v12.3.12): watchdog hand-off after final nudge pass ─────────────
# The nudge worker exhausts its owner-ping sequence at 168h, then goes silent.
# At that point the interview is still stalled but NO operator ever learns.
# Fix: after every nudge worker pass, if the interview is still incomplete AND
# idle >= ZHC_STUCK_INTERVIEW_DAYS threshold, invoke the operator escalation
# watchdog so the very cron that goes silent also wakes the operator lane.
# This keeps a single escalation source of truth (the watchdog) without the
# nudge cron doing any operator messaging itself (preserving the NO-FABRICATION
# / owner-only boundary).
_interview_still_incomplete=$(state_get '.interviewComplete')
ZHC_STUCK_INTERVIEW_DAYS="${ZHC_STUCK_INTERVIEW_DAYS:-5}"
if [[ "${_interview_still_incomplete}" != "true" ]] && (( HOURS_IDLE >= ZHC_STUCK_INTERVIEW_DAYS * 24 )); then
  WATCHDOG="${SCRIPT_DIR}/closeout-readiness-watchdog.sh"
  if [[ -f "$WATCHDOG" ]]; then
    log "nudge threshold elapsed and interview still incomplete - invoking closeout-readiness-watchdog (operator lane)"
    bash "$WATCHDOG" --from-nudge >>"${LOG_FILE}" 2>&1 || log "WARN: watchdog invocation returned non-zero (non-fatal)"
  else
    log "WARN: closeout-readiness-watchdog.sh not found at $WATCHDOG - skipping operator escalation"
  fi
fi

log "interview-nudge-cron complete"
exit 0
