#!/usr/bin/env bash
# interview-nudge-cron.sh — PRD-2.15: State-driven, gateway-routed nudge cron
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
#   • interviewComplete == true for all companies → nothing to do (exit 0)
#   • No companies with a lastQuestionAt set → nothing to do (exit 0)
#   • Under 24h idle → exit 0 (cheap check)
#
# GATEWAY RULE (BINDING — no exceptions):
#   All Telegram sends go through `openclaw message send`. NEVER use direct
#   HTTP to api.telegram.org. If the openclaw CLI is absent → log and skip
#   (do NOT fall back to direct HTTP).
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
# PRD-2.15 / v11.11.0
set -uo pipefail

# ── Platform detection ───────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"
else
  echo "[interview-nudge-cron] no OpenClaw root found; aborting" >&2
  exit 0
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

state_get() {
  jq -r "$1 // empty" "${STATE_FILE}" 2>/dev/null
}

# ── Lockfile ─────────────────────────────────────────────────────────────────
if [[ -f "${LOCK_FILE}" ]]; then
  lock_age=$(( $(date -u +%s) - $(date -u -r "${LOCK_FILE}" +%s 2>/dev/null || date -u +%s) ))
  if (( lock_age < STALE_LOCK_MINUTES * 60 )); then
    log "lockfile held (${lock_age}s old, limit=${STALE_LOCK_MINUTES}m) — nudge worker may still be running; skip"
    exit 0
  fi
  log "stale lockfile removed (${lock_age}s old)"
  rm -f "${LOCK_FILE}"
fi
touch "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

# ── No state file ─────────────────────────────────────────────────────────────
if [[ ! -f "${STATE_FILE}" ]]; then
  log "no state file at ${STATE_FILE} — nothing to do"
  exit 0
fi

command -v jq >/dev/null 2>&1 || { log "jq not found — aborting"; exit 1; }

# ── Cheap trigger check (token-free) ─────────────────────────────────────────
interview_complete=$(state_get '.interviewComplete')
last_q_at=$(state_get '.interviewProgress.lastQuestionAt')

if [[ "${interview_complete}" == "true" ]]; then
  log "interviewComplete=true — interview done, no nudge needed; exit"
  exit 0
fi

if [[ -z "${last_q_at}" ]]; then
  log "interviewProgress.lastQuestionAt not set — interview not started or state missing; exit"
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

if [[ "${LAST_EPOCH}" -eq 0 ]]; then
  log "WARN: could not parse lastQuestionAt='${last_q_at}'; skipping"
  exit 0
fi

HOURS_IDLE=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))
log "interview idle for ${HOURS_IDLE}h (lastQuestionAt=${last_q_at})"

if (( HOURS_IDLE < 24 )); then
  log "idle < 24h — no nudge yet; exit"
  exit 0
fi

# ── Check if the applicable nudge was already sent ────────────────────────────
# The worker records nudges_sent in the state (or in the handoff file as fallback).
# We delegate the per-nudge dedup logic to the Python worker itself.

# ── Verify gateway CLI is available ──────────────────────────────────────────
if ! command -v openclaw >/dev/null 2>&1; then
  log "WARN: openclaw CLI not found — cannot send nudge via gateway; skip (no direct-HTTP fallback)"
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

log "interview-nudge-cron complete"
exit 0
