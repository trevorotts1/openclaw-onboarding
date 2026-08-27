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

# F03: cron/launchd runs this with a minimal PATH (observed on this box:
# /usr/bin:/bin:/usr/sbin:/sbin has no /opt/homebrew/bin). Every bare
# `python3` call below would still resolve under that minimal PATH -- macOS
# ships a stub at /usr/bin/python3 -- but SILENTLY to a different
# interpreter (Apple's bundled Python) than the one this codebase is
# developed against at /opt/homebrew/bin/python3 on Apple Silicon (or
# /usr/local/bin on Intel). That is the same class of defect as a command
# that flat-out fails to resolve: a cron run behaves differently from an
# interactive run with nothing in the log to explain why. Prepend the known
# homebrew locations so both environments resolve the same interpreter;
# nothing is removed from whatever PATH cron/launchd already supplies (or
# the /usr/bin:/bin:/usr/sbin:/sbin fallback if PATH is unset, which set -u
# would otherwise reject).
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"

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

# Resolve the run roots -- run-root-agnostic (2026-08-27). The department
# tree is only ONE place runs live; PRESENTATION_RUNS_DIRS (colon-separated)
# adds more (e.g. ~/webinar-decks), and legacy PRESENTATION_RUNS_DIR still
# overrides the primary root. DOCTRINE: a root that does not exist or cannot
# be read is reported and skipped -- it is NEVER proof a run does not exist,
# and never a failure; the poll simply finds nothing there.
DEPT_RUNS_ROOT="${HOME}/.openclaw/workspace/departments/Presentations/runs"
RUNS_ROOT="${PRESENTATION_RUNS_DIR:-$DEPT_RUNS_ROOT}"

RUNS_ROOTS=""
if [ -n "${PRESENTATION_RUNS_DIRS:-}" ]; then
    IFS=":" read -r -a _CFG_ROOTS <<< "${PRESENTATION_RUNS_DIRS#!}"
    for _root in "${_CFG_ROOTS[@]}"; do
        [ -n "${_root}" ] || continue
        RUNS_ROOTS="${RUNS_ROOTS:+${RUNS_ROOTS}:}${_root}"
    done
fi
# Primary root always included unless the config list was exclusive ("!").
if [ "${PRESENTATION_RUNS_DIRS:-}" = "${PRESENTATION_RUNS_DIRS#!}" ]; then
    case ":${RUNS_ROOTS}:" in
        *":${RUNS_ROOT}:"*) ;;
        *) RUNS_ROOTS="${RUNS_ROOT}${RUNS_ROOTS:+:${RUNS_ROOTS}}" ;;
    esac
fi

for _root in ${RUNS_ROOTS//:/$'\n'}; do
    if [ ! -d "$_root" ]; then
        log "runs directory not found (skipping, NOT an error -- absence is not proof a run does not exist): $_root"
    fi
done

LAUNCHER="$SCRIPTS_DIR/presentation_job/launcher.py"
ENGINE_ENTRY="$SCRIPTS_DIR/presentation_job.py"

if [ ! -f "$LAUNCHER" ]; then
    log "engine launcher not found at $LAUNCHER -- cannot dispatch jobs"
    exit 2
fi

NEW_LAUNCHES=0
SKIPPED_RUNNING=0
SKIPPED_NO_INTAKE=0

# Walk every run directory under every configured runs root. One combined
# find across roots; duplicate run dirs (a root nested in another) are
# impossible in practice and harmless here (state.json checks are idempotent).
_RUNS_ROOTS_FIND_ARGS=()
for _root in ${RUNS_ROOTS//:/$'\n'}; do
    [ -d "$_root" ] && RUNS_ROOTS_FIND_ARGS+=("$_root")
done
if [ "${#RUNS_ROOTS_FIND_ARGS[@]}" -eq 0 ]; then
    log "no readable run roots; nothing to poll (UNDETERMINED, not a pass, not a failure)"
    log "scan complete: 0 launched"
    exit 0
fi
find "${RUNS_ROOTS_FIND_ARGS[@]}" -maxdepth 2 -type d -name "pres-*" 2>/dev/null | while read -r run_dir; do
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
        #
        # F03: launcher.py is a member of the presentation_job PACKAGE and
        # imports its siblings with a relative import (`from .vocab import
        # ...`). Invoking it BY FILE PATH (`python3 "$LAUNCHER"`) makes
        # Python treat it as a top-level script with no parent package, so
        # that import dies instantly with "attempted relative import with
        # no known parent package" -- proven on this box: `python3
        # presentation_job/launcher.py --check --run-dir <run>` ImportErrors
        # while `python3 -m presentation_job.launcher --check --run-dir
        # <run>` (run from SCRIPTS_DIR) does not. Every --resume dispatch
        # through the old file-path form died the same way, silently, so a
        # parked job could never actually resume. Run it as a module instead
        # -- `-m` requires the package's PARENT directory (SCRIPTS_DIR) to be
        # the working directory, so cd there in a subshell (parens) rather
        # than changing this script's own cwd.
        log "resuming parked job: $run_dir"
        ( cd "$SCRIPTS_DIR" && python3 -m presentation_job.launcher --resume --run-dir "$run_dir" ) 2>&1 | while IFS= read -r line; do
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
