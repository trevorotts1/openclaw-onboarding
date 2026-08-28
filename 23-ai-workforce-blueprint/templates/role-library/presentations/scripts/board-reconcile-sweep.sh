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

# 2026-08-27 scan-roots fix: additional scan roots come from configuration,
# never a hardcode -- SCAN_ROOTS_CONFIG (config file, one path per line) and/or
# PRESENTATION_SCAN_ROOTS (os.pathsep-separated). resolution + UNDETERMINED
# doctrine live in presentation_job/scan_roots.py.
ROOTS_FLAGS=""
if [ -n "${SCAN_ROOTS_CONFIG:-}" ]; then
  ROOTS_FLAGS="--roots-config ${SCAN_ROOTS_CONFIG}"
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep starting" >> "${LOG_FILE}"

python3 "${SCRIPT_DIR}/presentation_job.py" \
  --reconcile-board \
  --scan-root "${SCAN_ROOT}" \
  ${ROOTS_FLAGS:-} \
  --scan-depth "${SCAN_DEPTH}" \
  --max-age-hours "${MAX_AGE_HOURS}" \
  --apply \
  >> "${LOG_FILE}" 2>&1

rc=$?
if [ $rc -ne 0 ]; then
  echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep exited non-zero (exit $rc)" >> "${LOG_FILE}"
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep complete (exit $rc)" >> "${LOG_FILE}"
