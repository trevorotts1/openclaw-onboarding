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
# Run-root-agnostic (2026-08-27): the department tree is only ONE place runs
# live (this box also runs client decks at ~/webinar-decks/<client>/<deck>/<date>/).
# SCAN_ROOT stays the primary root; PRESENTATION_SCAN_ROOTS adds more
# (colon-separated; prefix "!" for exclusive). Absence inside any scanned root
# is NEVER proof a run does not exist -- the sweep reports UNDETERMINED
# (exit 10) and never blocks/heals/fails on path absence.
SCAN_ROOT="${SCAN_ROOT:-${HOME}/.openclaw/workspace/departments/Presentations/runs}"
SCAN_DEPTH="${SCAN_DEPTH:-3}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-72}"

EXTRA_ROOT_ARGS=""
if [ -n "${PRESENTATION_SCAN_ROOTS:-}" ]; then
  IFS=":" read -r -a _EXTRA_ROOTS <<< "${PRESENTATION_SCAN_ROOTS#!}"
  for _root in "${_EXTRA_ROOTS[@]}"; do
    [ -n "${_root}" ] || continue
    EXTRA_ROOT_ARGS="${EXTRA_ROOT_ARGS} --scan-root ${_root}"
  done
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep starting" >> "${LOG_FILE}"

# shellcheck disable=SC2086 -- EXTRA_ROOT_ARGS is a deliberate multi-word arg list
python3 "${SCRIPT_DIR}/presentation_job.py" \
  --reconcile-board \
  --scan-root "${SCAN_ROOT}" \
  ${EXTRA_ROOT_ARGS} \
  --scan-depth "${SCAN_DEPTH}" \
  --max-age-hours "${MAX_AGE_HOURS}" \
  --apply \
  >> "${LOG_FILE}" 2>&1

rc=$?
if [ $rc -ne 0 ]; then
  echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep exited non-zero (exit $rc)" >> "${LOG_FILE}"
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep complete (exit $rc)" >> "${LOG_FILE}"
