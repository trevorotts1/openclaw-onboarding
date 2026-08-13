#!/bin/sh
# presentation-watchdog.sh -- watchdog + board-reconcile + run-discovery pass.
# Called by launchd (com.blackceo.presentation-watchdog) with NO environment, so
# every path must default. The run root is where the engine writes state.json.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${1:-${LOG:-/dev/null}}"

# Default run root; overridable via environment (launchd EnvironmentVariables,
# see presentation-watchdog.plist.template -- the plist always passes SCAN_ROOT,
# and a deployed box installs this script from the same template, so the
# placeholder below is never the value a live run uses; the repo bans operator
# paths from committed files). Install must substitute the real run root.
SCAN_ROOT="${SCAN_ROOT:-<SCAN_ROOT>}"

# U14: PRESENTATION_NOTIFY_CMD is warn-not-crash by design (report.py, watchdog.py)
# so an unset transport fails silently everywhere else -- the operator/director
# never hear progress, blocked, or done, and stall findings below never leave
# this box. This script runs unattended via launchd with NO environment (see
# header), so this log is the only place that silence can surface. Loud, not
# fatal: matches the existing warn-mode idiom below, does not add set -e risk.
if [ -z "${PRESENTATION_NOTIFY_CMD:-}" ]; then
    echo "WARNING: PRESENTATION_NOTIFY_CMD is unset; watchdog stall notifications and job progress/blocked/done messages will not be delivered" >> "${LOG}" 2>&1
fi

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
# Exit 0  = scanned >=1 run dir, none raised, and >=1 was actually classified
#           (card_missing/card_behind/consistent/finished_no_card) -- a
#           genuine pass. NOTE (G5 fix): too_old no longer counts here --
#           it means the sweep DECLINED to inspect the run dir (found it
#           valid but too old to check further), not that anything was
#           reconciled. A too_old-only or too_old+not_a_run_dir-mixed scan
#           can still exit 0, but the log will carry an explicit
#           "reconciled 0 of N" WARNING line instead of reading as a clean
#           pass -- grep the log for "WARNING" if this box's decks are
#           ever unexpectedly stale.
# Exit 10 = zero run dirs found -- UNDETERMINED, not a pass, but a normal,
#           expected state between jobs -- must not abort this script before
#           the run-discovery pass below runs.
# Exit 11 = >=1 run dir raised an unexpected error while being
#           classified/reconciled -- also not a pass.
# Exit 12 = >=1 run dir found and none raised, but EVERY one was rejected by
#           Guard A (not_a_run_dir) -- zero were actually classified. Same
#           epistemic state as exit 10 (nothing could be checked), reached by
#           rejection instead of absence -- e.g. a STATE_SCHEMA_VERSION bump
#           that invalidates every real run dir on the box. Also not a pass,
#           and also a normal-enough state (a stale box) that this script
#           must keep going rather than abort.
# Captured explicitly (not swallowed) so a real problem is logged instead of
# silently reported as clean; kept non-fatal to this script on purpose so
# `set -e` cannot skip run-discovery just because no decks exist right now.
RECONCILE_RC=0
python3 "${SCRIPT_DIR}/presentation_job.py" \
    --reconcile-board \
    --scan-root "${SCAN_ROOT}" \
    >> "${LOG}" 2>&1 || RECONCILE_RC=$?
if [ "${RECONCILE_RC}" -ne 0 ]; then
    echo "WARNING: reconcile-board exited ${RECONCILE_RC} (0=pass; 10=zero run dirs/UNDETERMINED; 11=run dir failures; 12=all run dirs rejected/UNDETERMINED) -- NOT a pass, see reconcile-board lines above" >> "${LOG}" 2>&1
fi

# Run-discovery pass: optional component. Guarded with || true so a missing
# run_discovery.py cannot kill the loop.
python3 "${SCRIPT_DIR}/run_discovery.py" \
    --runs-root "${SCAN_ROOT}" \
    >> "${LOG}" 2>&1 || true
