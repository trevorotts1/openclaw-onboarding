#!/bin/bash
# board-reconcile-sweep.sh -- 15-minute board-card reconciliation
# Runs via cron at */15. Scans active runs and applies missing/behind
# board-card corrections (create + advance). Separate from the watchdog
# (which reports only without --apply) because writes should not fire
# every 5 minutes against a live card.
# Installed: 2026-08-10 per WORK-ITEM-04b MASTER-SPEC-2026-08-09.md FILE 5.
set -euo pipefail

# Source secrets for COMMAND_CENTER_URL, MC_API_TOKEN, WEBHOOK_SECRET.
# board_config() in cc_board.py reads COMMAND_CENTER_URL (preferred) or
# MISSION_CONTROL_URL (fallback) from the environment. Without this, every
# reconcile sweep is a no-op (board_disabled). Added 2026-08-10 per WI-04b fix.
if [ -f "${HOME}/.openclaw/secrets/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${HOME}/.openclaw/secrets/.env"
  set +a
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${HOME}/Library/Logs/openclaw/board-reconcile-sweep.log"
SCAN_ROOT="${SCAN_ROOT:-${HOME}/.openclaw/workspace/departments/Presentations/runs}"
SCAN_DEPTH="${SCAN_DEPTH:-3}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-72}"

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep starting" >> "${LOG_FILE}"

# FIX 37: use || to capture exit code despite set -e; the old pattern
# placed rc=$? after the python call, so set -e killed the script before
# reaching the error-reporting branch.
python3 "${SCRIPT_DIR}/presentation_job.py" \
  --reconcile-board \
  --scan-root "${SCAN_ROOT}" \
  --scan-depth "${SCAN_DEPTH}" \
  --max-age-hours "${MAX_AGE_HOURS}" \
  --apply \
  >> "${LOG_FILE}" 2>&1 && rc=0 || rc=$?

if [ $rc -ne 0 ]; then
  echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep exited non-zero (exit $rc)" >> "${LOG_FILE}"
  # FIX 37: emit error event to telemetry (consuming FIX 5 telemetry infra)
  TELEMETRY_DIR="${PRESENTATION_RUNS_DIR:-${HOME}/.openclaw/workspace/departments/Presentations}/telemetry"
  mkdir -p "$TELEMETRY_DIR"
  printf '{"event":"reconcile_error","generated_at":"%s","exit_code":%d,"scan_root":"%s"}\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$rc" "${SCAN_ROOT}" \
      >> "$TELEMETRY_DIR/events.jsonl"
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep complete (exit $rc)" >> "${LOG_FILE}"
