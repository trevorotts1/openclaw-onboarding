#!/bin/sh
# presentation-watchdog.sh -- wrapper the scheduler calls.
# ready-to-apply: NOT installed. See the ticket for install procedure (Named Stop).
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${1:-${LOG:-/dev/null}}"
exec timeout 300 python3 "${SCRIPT_DIR}/presentation_job.py" \
    --watchdog \
    --scan-root "${SCAN_ROOT:?SCAN_ROOT must be set}" \
    --grace "${GRACE:-1.5}" \
    --scan-depth "${SCAN_DEPTH:-3}" \
    >> "${LOG}" 2>&1
