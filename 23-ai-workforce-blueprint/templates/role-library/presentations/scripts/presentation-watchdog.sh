#!/bin/sh
# presentation-watchdog.sh -- watchdog + board-reconcile + run-discovery pass.
# Called by launchd (com.blackceo.presentation-watchdog) with NO environment, so
# every path must default. The run root is where the engine writes state.json.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${1:-${LOG:-/dev/null}}"

# Default run root; overridable via environment (launchd EnvironmentVariables).
SCAN_ROOT="${SCAN_ROOT:-/Users/blackceomacmini/.openclaw/workspace/departments/Presentations/runs}"

# Main watchdog pass. Warn mode by default (no --enforce): scans for stalled
# jobs and reports. Exit status is load-bearing -- set -e semantics preserved.
# launchd runs this with a minimal PATH (no /opt/homebrew/bin), so resolve the
# timeout wrapper explicitly; fall back to no wrapper if neither is present.
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_BIN="$(command -v timeout)"
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_BIN="$(command -v gtimeout)"
else
    echo "WARNING: neither timeout nor gtimeout found; watchdog run without a time limit" >> "${LOG}" 2>&1
fi

if [ -n "${TIMEOUT_BIN}" ]; then
    "${TIMEOUT_BIN}" 300 python3 "${SCRIPT_DIR}/presentation_job.py" \
        --watchdog \
        --scan-root "${SCAN_ROOT}" \
        --grace "${GRACE:-1.5}" \
        --scan-depth "${SCAN_DEPTH:-3}" \
        >> "${LOG}" 2>&1
else
    python3 "${SCRIPT_DIR}/presentation_job.py" \
        --watchdog \
        --scan-root "${SCAN_ROOT}" \
        --grace "${GRACE:-1.5}" \
        --scan-depth "${SCAN_DEPTH:-3}" \
        >> "${LOG}" 2>&1
fi

# Board-reconcile pass: report-only unless --apply is given.
python3 "${SCRIPT_DIR}/presentation_job.py" \
    --reconcile-board \
    --scan-root "${SCAN_ROOT}" \
    >> "${LOG}" 2>&1

# Run-discovery pass: optional component. Guarded with || true so a missing
# run_discovery.py cannot kill the loop.
python3 "${SCRIPT_DIR}/run_discovery.py" \
    --runs-root "${SCAN_ROOT}" \
    >> "${LOG}" 2>&1 || true
