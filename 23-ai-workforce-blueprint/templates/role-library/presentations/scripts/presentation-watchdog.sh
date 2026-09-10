#!/bin/sh
# presentation-watchdog.sh -- watchdog + board-reconcile + run-discovery pass.
# Called by launchd (com.blackceo.presentation-watchdog) with NO environment, so
# every path must default. The run root is where the engine writes state.json.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${1:-${LOG:-/dev/null}}"

# ---------------------------------------------------------------------------
# PRES-035 — native-tool fallback PATH + ONE pipeline interpreter for the tick.
# launchd hands this job essentially NO environment; the rendered plist
# carries BOTH Homebrew prefixes (Apple Silicon /opt/homebrew/bin + Intel
# /usr/local/bin) behind the system prefix, but a tick from a pre-PRES-035
# plist (or a hand invocation under a bare cron PATH) still needs the same
# discovery. Nothing is removed; the rendered/operator PATH survives intact.
# The interpreter pin (PRESENTATION_PIPELINE_INTERPRETER, rendered by
# install_watchdog_schedule and validated before render) wins; a NON-BLANK
# hand value wins for one invocation; the client venv is next; PATH python3
# is the last resort. Every `python3` below runs through the shim this block
# installs at the FRONT of PATH, so helpers, passes and spawned engines all
# use the validated pin with zero line changes. Rollback:
# PRESENTATION_PIPELINE_PIN=0 restores bare-PATH behavior.
# ---------------------------------------------------------------------------
case ":${PATH:-}:" in
    *":/opt/homebrew/bin:"*) ;;
    *) PATH="/opt/homebrew/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}" ;;
esac
case ":$PATH:" in
    *":/usr/local/bin:"*) ;;
    *) PATH="/usr/local/bin:$PATH" ;;
esac
export PATH
_PRES35_PIN="${PRESENTATION_PIPELINE_INTERPRETER:-}"
if [ "${PRESENTATION_PIPELINE_PIN:-1}" != "0" ] && [ -z "$_PRES35_PIN" ] \
    && [ -f "${SCRIPT_DIR}/presentation_job/pipeline_interp.py" ]; then
    _PRES35_PIN="$(cd "${SCRIPT_DIR}" && python3 -m presentation_job.pipeline_interp --resolve 2>/dev/null || true)"
fi
case "$_PRES35_PIN" in /*) ;;
    *) _PRES35_PIN="" ;;
esac
if [ -n "$_PRES35_PIN" ] && ! "$_PRES35_PIN" -c 'import sys' >/dev/null 2>&1; then
    echo "WARNING: [interp] schedule pin $_PRES35_PIN does not execute — falling back to PATH python3 for this tick; fix the pin or re-run update-skills.sh" >> "${LOG}" 2>&1
    _PRES35_PIN=""
fi
if [ -z "$_PRES35_PIN" ] && [ -n "${PRESENTATION_PIPELINE_INTERPRETER:-}" ]; then
    echo "WARNING: [interp] PRESENTATION_PIPELINE_INTERPRETER=${PRESENTATION_PIPELINE_INTERPRETER} unusable (missing or not executable) — fell through to PATH python3; fix the pin or re-run update-skills.sh" >> "${LOG}" 2>&1
fi
if [ -n "$_PRES35_PIN" ]; then
    PRESENTATION_PIPELINE_INTERPRETER="$_PRES35_PIN"
    export PRESENTATION_PIPELINE_INTERPRETER
    _PRES35_VER="$("$_PRES35_PIN" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null || echo unknown)"
    echo "[interp] pipeline interpreter: $_PRES35_PIN (Python $_PRES35_VER)" >> "${LOG}" 2>&1
    _PRES35_SHIM="${TMPDIR:-/tmp}/pres35-interp-shim-$$"
    if mkdir -p "$_PRES35_SHIM" 2>/dev/null \
        && printf '#!/bin/sh\nexec "%s" "$@"\n' "$_PRES35_PIN" > "$_PRES35_SHIM/python3" 2>/dev/null \
        && chmod +x "$_PRES35_SHIM/python3" 2>/dev/null; then
        PATH="$_PRES35_SHIM:$PATH"
        export PATH
        echo "[interp] shim installed: python3 -> $_PRES35_PIN" >> "${LOG}" 2>&1
    else
        echo "WARNING: [interp] shim install failed — bare python3 resolves via PATH (tick continues, pin exported)" >> "${LOG}" 2>&1
    fi
    unset _PRES35_SHIM
    # Scheduler readiness receipt: actual sys.executable/version + required
    # import proof vs the rendered pin; mismatch degrades with bounded
    # remediation instead of reusing stale proof.
    if [ -f "${SCRIPT_DIR}/presentation_job/pipeline_interp.py" ] && [ "${SCAN_ROOT:-}" != "<SCAN_ROOT>" ] && [ -d "${SCAN_ROOT:-}" ]; then
        ( cd "${SCRIPT_DIR}" && python3 -m presentation_job.pipeline_interp --check-readiness --scheduler watchdog --recorded "${PRESENTATION_PIPELINE_INTERPRETER:-}" --runs-root "${SCAN_ROOT}" 2>&1 ) \
            | while IFS= read -r _pres35_line; do
                echo "[interp] ${_pres35_line}" >> "${LOG}" 2>&1
            done || true
    fi
else
    echo "WARNING: [interp] no validated pipeline interpreter — bare python3 resolves via PATH (pre-PRES-035 behavior)" >> "${LOG}" 2>&1
fi
unset _PRES35_PIN _PRES35_VER

# ---------------------------------------------------------------------------
# ENV STORE -- this file's own header already says it: "Called by launchd with
# NO environment". Every path defaults, but the CREDENTIALS never did.
#
# The FIX 22 gate 30 lines below refuses the entire watchdog pass (exit 4,
# AF-NOTIFY-UNCONFIGURED) when PRESENTATION_NOTIFY_CMD is unset -- and under
# launchd it is unset even on a box where the value is present and non-blank
# in every env store, because nothing here ever loaded one. That is the same
# ENV-LOADING defect measured on presentation-intake-poll.sh (5,948
# consecutive refusals, 2026-09-06), in the sibling launchd entry point.
#
# Load the store FIRST, so the gate below judges a real environment. Loading
# it cannot weaken the gate: a box that genuinely has no transport anywhere
# still refuses, and now the log says which stores were searched.
#
# Precedence is process-env-wins (a value already set NON-BLANK is never
# overwritten), so the plist's own EnvironmentVariables and a one-off
# `PRESENTATION_NOTIFY_CMD=... sh presentation-watchdog.sh` both still win.
# The loader emits shlex-quoted `export` lines on stdout only -- no value
# reaches ${LOG}; the report that does is paths, counts and presence+LENGTH.
#
# POSIX sh only (this script is #!/bin/sh and runs under dash in a container),
# and every step is `||`-guarded because this script runs under `set -e`: a
# loader that cannot run must degrade to the pre-fix behaviour, never abort
# the watchdog pass it exists to enable.
# Rollback: PRESENTATION_ENV_STORE=0.
# ---------------------------------------------------------------------------
if [ -f "${SCRIPT_DIR}/presentation_job/env_store.py" ]; then
    _ENV_RC=0
    _ENV_SH="$( cd "${SCRIPT_DIR}" && python3 -m presentation_job.env_store --emit-shell 2>/dev/null )" || _ENV_RC=$?
    if [ "${_ENV_RC}" -eq 0 ]; then
        eval "${_ENV_SH}" || echo "WARNING: env-store assignments could not be applied -- continuing with the environment launchd supplied" >> "${LOG}" 2>&1
        unset _ENV_SH
        ( cd "${SCRIPT_DIR}" && python3 -m presentation_job.env_store --report 2>&1 ) \
            | while IFS= read -r _env_line; do
                echo "[env-store] ${_env_line}" >> "${LOG}" 2>&1
            done || true
    else
        unset _ENV_SH
        echo "[env-store] loader exited rc=${_ENV_RC} -- the env store was NOT loaded and nothing was exported" >> "${LOG}" 2>&1
    fi
else
    echo "[env-store] presentation_job/env_store.py NOT FOUND under ${SCRIPT_DIR} -- the env store was not loaded (partial deploy)" >> "${LOG}" 2>&1
fi

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

# ---------------------------------------------------------------------------
# F13 -- UNDELIVERABLE-MESSAGE SWEEP PASS.
#
# report.py queues every message it could not deliver into
# state["undeliverable"] (FAULT-14) so it can be retried later. "Later" had no
# driver: cmd_sweep_undeliverable_roots -- the only sweep that works from a
# scan root instead of a --run-dir a human must already know -- was scheduled
# by nothing, in no plist, no cron and no installer. A client notice that
# missed its window (the measured run's "your presentation is paused") sat in
# the queue forever, and the operator was never told the run had stalled.
# This is the schedule.
#
# Runs LAST, after run-discovery, on purpose: the four passes above can each
# queue a fresh notice during THIS tick, and sweeping after them retries it in
# the same tick instead of five minutes later.
#
# Bounded by construction, so an unattended tick cannot spin:
#   - MAX_DELIVERY_ATTEMPTS = 5 (presentation_job/__main__.py) dead-letters a
#     message that fails five sweeps into state["dead_letter"] -- quarantined
#     with its reason, never retried again and never silently dropped.
#   - a run dir whose lock a live engine holds is SKIPPED, not contended; it
#     is swept on a later tick.
#
# Exit status CAPTURED, never left to `set -e` -- same treatment and the same
# reason as the watchdog/reconcile/supervise blocks above: 0 = pass,
# 11 = at least one run dir raised an unexpected error.
# ---------------------------------------------------------------------------
SWEEP_RC=0
python3 "${SCRIPT_DIR}/presentation_job.py" \
    --sweep-undeliverable-roots \
    --scan-root "${SCAN_ROOT}" \
    ${ROOTS_FLAGS} \
    --scan-depth "${SCAN_DEPTH:-3}" \
    >> "${LOG}" 2>&1 || SWEEP_RC=$?
if [ "${SWEEP_RC}" -ne 0 ]; then
    echo "WARNING: undeliverable sweep exited ${SWEEP_RC} (0=pass; 11=>=1 run dir raised an unexpected error) -- see the sweep lines above" >> "${LOG}" 2>&1
fi
