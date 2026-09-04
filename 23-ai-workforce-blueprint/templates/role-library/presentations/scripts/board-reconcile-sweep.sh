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

# FIX 61 (exit handling, W15b-B3): the starting line must never be able to
# abort the script under `set -e` (an unwritable LOG_FILE dir used to kill the
# sweep before the python call ever ran, and cron logged nothing after that).
LOG_DIR="$(dirname "${LOG_FILE}")"
mkdir -p "${LOG_DIR}" 2>/dev/null || true
echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep starting" >> "${LOG_FILE}" || true

# FIX 37: use || to capture exit code despite set -e; the old pattern
# placed rc=$? after the python call, so set -e killed the script before
# reaching the error-reporting branch.
python3 "${SCRIPT_DIR}/presentation_job.py" \
  --reconcile-board \
  --scan-root "${SCAN_ROOT}" \
  ${ROOTS_FLAGS:-} \
  --scan-depth "${SCAN_DEPTH}" \
  --max-age-hours "${MAX_AGE_HOURS}" \
  --apply \
  >> "${LOG_FILE}" 2>&1 && rc=0 || rc=$?

if [ $rc -ne 0 ]; then
  echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep exited non-zero (exit $rc)" >> "${LOG_FILE}" || true
  # FIX 37: emit error event to telemetry (consuming FIX 5 telemetry infra).
  # FIX 61: bounded -- a telemetry write that cannot happen (unwritable dir)
  # must not trip `set -e` and mask the real reconcile exit code below.
  TELEMETRY_DIR="${PRESENTATION_RUNS_DIR:-${HOME}/.openclaw/workspace/departments/Presentations}/telemetry"
  mkdir -p "$TELEMETRY_DIR" 2>/dev/null || true
  printf '{"event":"reconcile_error","generated_at":"%s","exit_code":%d,"scan_root":"%s"}\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$rc" "${SCAN_ROOT}" \
      >> "$TELEMETRY_DIR/events.jsonl" 2>/dev/null || \
      echo "WARNING: reconcile_error telemetry write failed" >> "${LOG_FILE}" 2>/dev/null || true
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S')] board-reconcile-sweep complete (exit $rc)" >> "${LOG_FILE}" || true

# FIX 61 (W15b-B3): the script previously ALWAYS exited 0 -- the final `echo`
# was its last command, so cron/launchd and any supervisor could never see a
# failed reconcile tick. Propagate the python reconcile exit contract now:
#   0  pass; 10 EXIT_SWEEP_NO_RUNS (zero run dirs -- UNDETERMINED, a normal
#      empty-department state, reported but not failed); 11
#      EXIT_SWEEP_HAD_FAILURES; 12 EXIT_SWEEP_ALL_REJECTED. 10 is normalized
#      to 0 here because the sweep has already logged/telemetrized the
#      UNDETERMINED state (the script's own error branch above) and an empty
#      department is not a cron failure; 11/12 propagate as real failures.
# The exit line is guarded with || 0 so `set -e` cannot make the script's very
# last act re-mask the code it is reporting.
if [ "$rc" -eq 10 ]; then
  exit 0
fi
exit "$rc" || exit 0
