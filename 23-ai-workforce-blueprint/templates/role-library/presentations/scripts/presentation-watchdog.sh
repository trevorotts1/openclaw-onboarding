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

# FIX 22 (presentation rev2 waves): an unset PRESENTATION_NOTIFY_CMD is a
# hard configuration error at launch, not a warning. The U14 warn-mode idiom
# this block replaced is exactly what let a stalled job sit silently on a box:
# the watchdog pass ran, found the stall, and its finding could never leave.
# Fail-closed is the DEFAULT (PRESENTATION_NOTIFY_FAIL_CLOSED unset or any
# value other than "0"): log the AF-NOTIFY-UNCONFIGURED payload carrying the
# NOT_READY_NOTIFY marker (the string FIX 39's pre-roll gate keys on) and
# exit 4 BEFORE any pass runs -- exit 4 is distinct from the watchdog pass's
# own 5/13 and reconcile-board's 10-12. PRESENTATION_NOTIFY_FAIL_CLOSED=0 is
# the documented EMERGENCY rollback: it restores the pre-fix warn-and-continue
# line below for one hour per the rollout doctrine, does NOT restore direct
# Telegram (FIX 23 owns the transport), and does NOT suppress FIX 21
# SYSTEM-block notifications.
NOTIFY_FAIL_CLOSED="${PRESENTATION_NOTIFY_FAIL_CLOSED:-1}"

# 2026-08-27 scan-roots fix: one scan root was the blind spot -- a client deck
# built outside the department tree was invisible to all three passes below.
# EXTRA scan roots now come from configuration, never a hardcode:
#   - PRESENTATION_SCAN_ROOTS: os.pathsep-separated additional roots, and/or
#   - a config file (SCAN_ROOTS_CONFIG, default <department>/config/scan-roots.conf)
#     with one absolute path per line (#-comments allowed).
# The python passes resolve and log the full root list every run; a root that
# cannot be read is reported UNDETERMINED, never treated as "no runs here".
# A box adds roots by editing its own config file -- no code change.
ROOTS_FLAGS=""
if [ -n "${SCAN_ROOTS_CONFIG:-}" ]; then
    ROOTS_FLAGS="--roots-config ${SCAN_ROOTS_CONFIG}"
fi

if [ -z "${PRESENTATION_NOTIFY_CMD:-}" ]; then
    if [ "${NOTIFY_FAIL_CLOSED}" != "0" ]; then
        echo "AF-NOTIFY-UNCONFIGURED: PRESENTATION_NOTIFY_CMD is unset -- refusing to run the watchdog pass (fail-closed)" >> "${LOG}" 2>&1
        echo "NOT_READY_NOTIFY: watchdog stall notifications and job progress/blocked/done messages cannot leave this box. Set PRESENTATION_NOTIFY_CMD (e.g. to presentation-notify.py) or set PRESENTATION_NOTIFY_FAIL_CLOSED=0 for the documented emergency rollback." >> "${LOG}" 2>&1
        exit 4
    fi
    echo "WARNING: PRESENTATION_NOTIFY_CMD is unset; watchdog stall notifications and job progress/blocked/done messages will not be delivered" >> "${LOG}" 2>&1
elif [ "${NOTIFY_FAIL_CLOSED}" != "0" ] && \
     [ -f "${SCRIPT_DIR}/presentation_job/notify_preflight.py" ]; then
    # Set but possibly unusable (unparseable argv / empty after tokenising):
    # single-source the structural verdict through notify_preflight -- the
    # same module the launcher's notify_gate and FIX 39's pre-roll gate use --
    # so "what counts as configured" cannot drift between sh and python. The
    # CLI's fail-closed exit is 8; any nonzero here is a refusal. If the
    # module itself cannot run, behave as configured (same as the launcher's
    # missing-module path): warn-and-continue, never fail-open silently.
    if ! python3 "${SCRIPT_DIR}/presentation_job/notify_preflight.py" >> "${LOG}" 2>&1; then
        echo "AF-NOTIFY-UNCONFIGURED: PRESENTATION_NOTIFY_CMD is set but unusable -- refusing to run the watchdog pass (fail-closed)" >> "${LOG}" 2>&1
        echo "NOT_READY_NOTIFY: fix the transport command, or set PRESENTATION_NOTIFY_FAIL_CLOSED=0 for the documented emergency rollback." >> "${LOG}" 2>&1
        exit 4
    fi
fi

# Main watchdog pass. Warn mode by default (no --enforce): scans for stalled
# jobs and reports.
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

# Exit status is load-bearing but explicitly CAPTURED, not left to `set -e`
# (B5 fix companion): watchdog() can now return EXIT_WATCHDOG_NO_RUNS (13)
# when it scans zero state.json files -- a normal, expected state between
# jobs, same as reconcile-board's exit 10 below -- and, once stage 3 wires
# --enforce in here, EXIT_STALLED (5) on a real stall. Before this fix, an
# uncaptured nonzero exit here would trip `set -e` and abort the script
# immediately, skipping the reconcile-board pass AND the run-discovery pass
# below -- exactly the failure mode the reconcile-board block already guards
# against one paragraph down. Same treatment, same reason, applied here too.
WATCHDOG_RC=0
if [ -n "${TIMEOUT_BIN}" ]; then
    "${TIMEOUT_BIN}" 300 python3 "${SCRIPT_DIR}/presentation_job.py" \
        --watchdog \
        --scan-root "${SCAN_ROOT}" \
        ${ROOTS_FLAGS} \
        --grace "${GRACE:-1.5}" \
        --scan-depth "${SCAN_DEPTH:-3}" \
        >> "${LOG}" 2>&1 || WATCHDOG_RC=$?
else
    python3 "${SCRIPT_DIR}/presentation_job.py" \
        --watchdog \
        --scan-root "${SCAN_ROOT}" \
        ${ROOTS_FLAGS} \
        --grace "${GRACE:-1.5}" \
        --scan-depth "${SCAN_DEPTH:-3}" \
        >> "${LOG}" 2>&1 || WATCHDOG_RC=$?
fi
if [ "${WATCHDOG_RC}" -ne 0 ]; then
    echo "WARNING: watchdog exited ${WATCHDOG_RC} (0=pass; 5=stalled+enforce; 13=zero state.json found/UNDETERMINED) -- NOT necessarily a failure, see watchdog lines above" >> "${LOG}" 2>&1
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
    ${ROOTS_FLAGS} \
    >> "${LOG}" 2>&1 || RECONCILE_RC=$?
if [ "${RECONCILE_RC}" -ne 0 ]; then
    echo "WARNING: reconcile-board exited ${RECONCILE_RC} (0=pass; 10=zero run dirs/UNDETERMINED; 11=run dir failures; 12=all run dirs rejected/UNDETERMINED) -- NOT a pass, see reconcile-board lines above" >> "${LOG}" 2>&1
fi

# Worker-liveness supervision pass (supervisor.py, 2026-08-27): detects an
# engine PROCESS that died mid-run behind an active (non-terminal, .job.lock
# present) run -- the death the 2026-08-27 live deck suffered with nothing
# noticing -- and restarts it under a bounded, exponentially-backed-off
# budget. Report-only WITHOUT --apply (same staging discipline as
# reconcile-board: a pass that can start processes proves itself in the log
# first); flip to --apply once its report-only output has been watched for a
# cycle. Exit codes are documented in state.py: 0=pass (or alarm cleared),
# 14=zero state.json found (UNDETERMINED), 15=>=1 run exhausted its restart
# budget and is ALARMING. Captured, not swallowed, and never fatal to the
# run-discovery pass below -- same set -e treatment as the two passes above.
SUPERVISE_RC=0
python3 "${SCRIPT_DIR}/presentation_job.py" \
    --supervise \
    --scan-root "${SCAN_ROOT}" \
    --scan-depth "${SCAN_DEPTH:-3}" \
    ${PRESENTATION_SUPERVISE_APPLY:+--apply} \
    --max-restarts "${SUPERVISOR_MAX_RESTARTS:-3}" \
    --supervisor-backoff "${SUPERVISOR_BACKOFF_SECONDS:-60}" \
    >> "${LOG}" 2>&1 || SUPERVISE_RC=$?
if [ "${SUPERVISE_RC}" -ne 0 ]; then
    echo "WARNING: supervise exited ${SUPERVISE_RC} (0=pass; 14=zero state.json found/UNDETERMINED; 15=restart budget exhausted/ALARM) -- NOT necessarily a failure, see supervisor lines above" >> "${LOG}" 2>&1
fi

# Run-discovery pass: optional component. Guarded with || true so a missing
# run_discovery.py cannot kill the loop. It resolves the same root list as the
# two passes above (SCAN_ROOT + PRESENTATION_SCAN_ROOTS + the config file) and
# walks each root to --scan-depth, so a run three levels down is found too.
python3 "${SCRIPT_DIR}/run_discovery.py" \
    --runs-root "${SCAN_ROOT}" \
    ${ROOTS_FLAGS} \
    --scan-depth "${SCAN_DEPTH:-3}" \
    >> "${LOG}" 2>&1 || true

# FIX 64 (one notification transport): the SCHEDULED undeliverable retry.
# report.py queues every FAILED/UNDETERMINED transport attempt (a stall alert
# whose send timed out, a blocked notice the transport could not deliver) into
# state["undeliverable"]; until now that queue had no driver on a tick -- a
# human had to run the sweep by hand against a run dir they had to know. This
# pass is that driver, scheduled from the watchdog tick itself:
#   --sweep-undeliverable-roots  resolves the same root list as every other
#       pass here (SCAN_ROOT, packed or not, + PRESENTATION_SCAN_ROOTS + the
#       config file), finds each run dir holding a queued message, and runs
#       the same per-run retry logic (run lock, dead-letter cap at
#       MAX_DELIVERY_ATTEMPTS) -- by delegation in cmd_sweep_undeliverable_
#       roots, never a re-derived copy.
# Fail-soft by construction: a lock held by a live engine is SKIPPED (counted,
# retried next tick), one bad run dir never ends the pass, and a nonzero exit
# is captured and logged without aborting -- same discipline as the three
# passes above. Exit codes: 0 = pass (including nothing to retry), 11 = >=1
# run dir failed unexpectedly.
SWEEP_RC=0
python3 "${SCRIPT_DIR}/presentation_job.py" \
    --sweep-undeliverable-roots \
    --scan-root "${SCAN_ROOT}" \
    ${ROOTS_FLAGS} \
    --scan-depth "${SCAN_DEPTH:-3}" \
    >> "${LOG}" 2>&1 || SWEEP_RC=$?
if [ "${SWEEP_RC}" -ne 0 ]; then
    echo "WARNING: sweep-undeliverable-roots exited ${SWEEP_RC} (0=pass; 11=run dir failures) -- queued alerts will retry next tick, see sweep lines above" >> "${LOG}" 2>&1
fi

# FIX 19 (MASTER Part 8): the SCHEDULED stray-orphan reaper. SIGTERM-mid-wave
# QC proof: killing an engine left its auto-spawned dispatcher, prompt-wave
# workers, and render children alive -- they kept rewriting intake, and until
# now the reaper had to be run BY HAND against a run dir the operator had to
# know. This pass is that scheduler, one reap per watchdog tick:
#   process_reaper.py --scan-root "${SCAN_ROOT}"
# classifies every process on the box (FIX 19: dispatcher/worker argv shapes
# in BOTH the script form and the `-m` module form are build-shaped) against
# its run dir's liveness, and REAPS the strays -- children included, via
# reap_strays()'s descendant-tree kill. A live run's processes classify
# REAL_BUILD and are never touched, so this is safe to run every tick,
# including while a build is mid-wave.
# Fail-soft by construction, same discipline as the passes above: a nonzero
# exit is captured and logged without aborting (and there IS no later pass to
# protect, so ordering here is last). Exit codes: 0 = clean pass (no strays),
# 1 = ran and killed >=1 stray (the evidence JSON records before/after
# tables), 2 = argparse usage. PRESENTATION_REAPER_DISABLE=1 is the documented
# operator rollback: skip the pass entirely (never a bare reaper on a box
# that needs to debug its own process table).
if [ "${PRESENTATION_REAPER_DISABLE:-0}" != "1" ] && [ -f "${SCRIPT_DIR}/process_reaper.py" ]; then
    REAPER_RC=0
    python3 "${SCRIPT_DIR}/process_reaper.py" \
        --scan-root "${SCAN_ROOT}" \
        >> "${LOG}" 2>&1 || REAPER_RC=$?
    if [ "${REAPER_RC}" -ne 0 ]; then
        echo "WARNING: process_reaper exited ${REAPER_RC} (0=no strays; 1=stays reaped, see evidence JSON; 2=usage) -- orphan sweep ran this tick, see reaper lines above" >> "${LOG}" 2>&1
    fi
fi
