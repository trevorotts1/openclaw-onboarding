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
#   • interviewComplete == true → self-remove this cron + exit 0 (no nudge)
#   • No companies with a lastQuestionAt set → nothing to do (exit 0)
#   • Under 24h idle → exit 0 (cheap check)
#
# GATEWAY RULE (BINDING — no exceptions):
#   All Telegram sends go through `openclaw message send`. NEVER use direct
#   direct Telegram Bot API calls. If the openclaw CLI is absent → log and skip
#   (do NOT fall back to direct HTTP).
#
# OPERATOR-ANNOUNCE RULE (BINDING — v12.3.10):
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
#   client — even on boxes installed before run-closeout.sh's primary removal path.
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

state_get() {
  jq -r "$1 // empty" "${STATE_FILE}" 2>/dev/null
}

state_set() {
  local tmp
  tmp=$(mktemp)
  if jq "$1" "${STATE_FILE}" > "$tmp" 2>/dev/null; then
    mv "$tmp" "${STATE_FILE}"
  else
    rm -f "$tmp"
    log "state_set failed for: $1"
    return 1
  fi
}

# ── Self-removal (v12.3.10) ───────────────────────────────────────────────────
# Find the cron UUID from state (preferred) or by name-scan (fallback for
# boxes installed before UUID recording was added — e.g. Talaya).
find_nudge_cron_uuid() {
  if [[ -f "${STATE_FILE}" ]] && command -v jq >/dev/null 2>&1; then
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
    log "self_remove_cron($reason): could not find interview-nudge cron UUID — may already be removed"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if command -v openclaw >/dev/null 2>&1; then
    openclaw cron rm "$uuid" 2>>"${LOG_FILE}" || log "WARN: cron rm failed (tolerated)"
  fi
  # Clear UUID from build-state
  if [[ -f "${STATE_FILE}" ]]; then
    state_set 'del(.interviewNudgeUuid) | .interviewNudgeRegisteredAt = null' 2>/dev/null || true
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
  log "interviewComplete=true — interview done, no nudge needed; self-removing cron"
  self_remove_cron "interviewComplete"
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
    log "nudge threshold elapsed and interview still incomplete — invoking closeout-readiness-watchdog (operator lane)"
    bash "$WATCHDOG" --from-nudge >>"${LOG_FILE}" 2>&1 || log "WARN: watchdog invocation returned non-zero (non-fatal)"
  else
    log "WARN: closeout-readiness-watchdog.sh not found at $WATCHDOG — skipping operator escalation"
  fi
fi

log "interview-nudge-cron complete"
exit 0
