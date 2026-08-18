#!/usr/bin/env bash
# WORK-ITEM-02: Intake-completion poller for the Presentations department.
#
# This script polls for intake interviews that have completed (intake_ledger.json
# with status=complete) but where the engine has NOT yet been launched for the
# corresponding run directory. When it finds one, it dispatches the engine.
#
# Runs via launchd or cron on a 5-minute interval (same cadence as the watchdog).
# This is the mechanical bridge between a finished intake interview and the engine
# that builds the deck -- the gap at the heart of WORK-ITEM-02 ("the intake cron,
# canonical entry, and CC all stop short").
#
# Exit codes:
#   0 - scan completed (may or may not have found jobs to launch)
#   2 - launcher module not found
#   The engine's own exit code does NOT affect this script -- it spawns the engine
#   in the background and returns immediately.

set -uo pipefail

PROG="presentation-intake-poll.sh"
# Resolve SCRIPTS_DIR relative to this script, via the canonical OC workspace
_resolve_scripts_dir() {
    local candidate
    # 1) This script's own dir (when already in the dept workspace)
    candidate="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
    if [ -f "$candidate/presentation_job.py" ]; then echo "$candidate"; return 0; fi
    # 2) Canonical agent workspace (OC_WS_RESOLVED is set by openclaw)
    candidate="${OC_WS_RESOLVED:-${HOME}/.openclaw/workspace}/departments/Presentations/scripts"
    if [ -f "$candidate/presentation_job.py" ]; then echo "$candidate"; return 0; fi
    # 3) OC config root fallback
    candidate="${OPENCLAW_CONFIG_ROOT:-${HOME}/.openclaw}/workspace/departments/Presentations/scripts"
    if [ -f "$candidate/presentation_job.py" ]; then echo "$candidate"; return 0; fi
    return 1
}
SCRIPTS_DIR="$(_resolve_scripts_dir)" || { log "cannot resolve scripts dir"; exit 2; }
LOG_FILE="${HOME}/Library/Logs/openclaw/presentation-intake-poll.log"

log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') [$PROG] $*" | tee -a "$LOG_FILE"
}

# Resolve the runs root
RUNS_ROOT="${PRESENTATION_RUNS_DIR:-${HOME}/.openclaw/workspace/departments/Presentations/runs}"

if [ ! -d "$RUNS_ROOT" ]; then
    log "runs directory not found: $RUNS_ROOT"
    exit 0
fi

LAUNCHER="$SCRIPTS_DIR/presentation_job/launcher.py"
ENGINE_ENTRY="$SCRIPTS_DIR/presentation_job.py"

if [ ! -f "$LAUNCHER" ]; then
    log "engine launcher not found at $LAUNCHER -- cannot dispatch jobs"
    exit 2
fi

NEW_LAUNCHES=0
SKIPPED_RUNNING=0
SKIPPED_NO_INTAKE=0

# Walk every run directory under $RUNS_ROOT.
find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" 2>/dev/null | while read -r run_dir; do
    INTAKE_LEDGER="$run_dir/working/interview/intake_ledger.json"
    STATE_JSON="$run_dir/state.json"

    # Must have a completed intake ledger
    if [ ! -f "$INTAKE_LEDGER" ]; then
        continue
    fi

    # Check intake completeness
    INTAKE_COMPLETE=0
    if command -v python3 >/dev/null 2>&1; then
        INTAKE_COMPLETE=$(python3 -c "
import json, sys
try:
    d = json.load(open('$INTAKE_LEDGER'))
    status = d.get('status') or d.get('complete')
    if status == 'complete' or status is True or str(status).lower() == 'true':
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
" 2>/dev/null && echo 1 || echo 0)
    fi

    if [ "$INTAKE_COMPLETE" -eq 0 ]; then
        continue
    fi

    # Check if the engine has already been launched for this run
    if [ -f "$STATE_JSON" ] && command -v python3 >/dev/null 2>&1; then
        TERMINAL=$(python3 -c "
import json, sys
try:
    s = json.load(open('$STATE_JSON'))
    print(s.get('terminal',''))
except Exception:
    print('')
" 2>/dev/null)
        if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "BLOCKED" ]; then
            # Already finished or parked -- skip
            continue
        fi

        # Check if already running (PID exists + alive)
        PID=$(python3 -c "
import json, sys
try:
    s = json.load(open('$STATE_JSON'))
    print(s.get('engine_pid',''))
except Exception:
    print('')
" 2>/dev/null)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            # Already running
            continue
        fi

        # state.json exists but engine is not running -- this is a parked/resume
        # candidate. Launch with --resume.
        log "resuming parked job: $run_dir"
        python3 "$LAUNCHER" --resume --run-dir "$run_dir" 2>&1 | while IFS= read -r line; do
            log "  $line"
        done
        NEW_LAUNCHES=$((NEW_LAUNCHES + 1))
    else
        # No state.json -- this intake completed but the engine was never launched.
        # Build an intake JSON and create a new engine job.
        log "new intake complete, dispatching engine: $run_dir"

        # fix/deck-type-routing-bypass: this used to build the intake JSON
        # inline with NO deck-type normalization at all (`ptype =
        # ledger.get('presentation_type') or 'from_scratch'`), so a ledger
        # carrying "signature_presentation" (the SOP's own `deck_type` name
        # for what the engine calls "signature") was handed to the engine
        # unresolved, --new rejected it, no state.json was written, and this
        # loop (which always `exit 0`s -- see below) retried the identical
        # failure every 5 minutes, forever, with nothing but a WARNING line
        # to show for it. Resolve through the SAME shared resolver the
        # canonical entry script uses (single-sourced vocabulary, see
        # vocab.py) -- an unresolvable deck type is now a loud ERROR here,
        # not a silent default that would build the WRONG deck.
        ENGINE_INTAKE_TMP="$run_dir/working/checkpoints/.engine-intake.json"
        mkdir -p "$(dirname "$ENGINE_INTAKE_TMP")"
        RESOLVE_OUT="$(python3 "$SCRIPTS_DIR/presentation_job/resolve_intake.py" \
            --ledger "$INTAKE_LEDGER" --out "$ENGINE_INTAKE_TMP" \
            --source intake-poll 2>&1)"
        if [ $? -ne 0 ]; then
            log "  ERROR: $run_dir did not resolve to a legal presentation_type: $RESOLVE_OUT"
            log "  skipping this run dir until its intake ledger is corrected -- it will NOT silently build the wrong deck type"
            continue
        fi
        log "  $RESOLVE_OUT"

        # Create the engine job then run it
        python3 "$ENGINE_ENTRY" --new --run-dir "$run_dir" --intake "$ENGINE_INTAKE_TMP" 2>&1 | while IFS= read -r line; do
            log "  [create] $line"
        done

        if [ -f "$run_dir/state.json" ]; then
            # Engine job created -- now launch the run (background).
            # We use Python subprocess here because poll.sh itself must return quickly.
            python3 -c "
import subprocess, sys, os
argv = [sys.executable or 'python3', '$ENGINE_ENTRY', '--run', '--run-dir', '$run_dir']
log_dir = os.path.join('$run_dir', 'working', 'logs')
os.makedirs(log_dir, exist_ok=True)
out = open(os.path.join(log_dir, 'engine-stdout.log'), 'a')
err = open(os.path.join(log_dir, 'engine-stderr.log'), 'a')
proc = subprocess.Popen(argv, cwd='$SCRIPTS_DIR', stdout=out, stderr=err,
                        start_new_session=True, close_fds=True)
print(f' {proc.pid}', end='')
# Write the PID to state.json so the watchdog can monitor it
import json
sp = os.path.join('$run_dir', 'state.json')
if os.path.isfile(sp):
    state = json.load(open(sp))
    state['engine_pid'] = proc.pid
    json.dump(state, open(sp + '.tmp', 'w'), indent=2)
    os.replace(sp + '.tmp', sp)
" 2>&1 | while IFS= read -r line; do
                log "  [run] $line"
            done
            NEW_LAUNCHES=$((NEW_LAUNCHES + 1))
        else
            log "  WARNING: engine --new succeeded but state.json not found -- engine not launched"
        fi
    fi
done

log "scan complete: $NEW_LAUNCHES launched"
exit 0
