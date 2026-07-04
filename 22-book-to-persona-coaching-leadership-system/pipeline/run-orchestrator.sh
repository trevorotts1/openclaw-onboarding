#!/usr/bin/env bash
# run-orchestrator.sh — launch the book-to-persona orchestrator DETACHED but
# fully REAPABLE (orphan-process prevention, fleet-wide).
#
# THE ORPHAN BUG this closes: an agent copies orchestrator.py to
# orchestrator_<slug>.py and runs it in the background; when the agent is
# stopped, the detached Python child reparents to launchd/init and keeps making
# :cloud calls until it finishes, billing the client. Launch through THIS script
# and that can't happen:
#   • the child runs in its OWN session/process group (setsid) so it is reapable
#     as a unit, and its own children (Phase-5 indexer, etc.) die with it;
#   • a liveness LOCKFILE is created here and removed on EXIT/INT/TERM/HUP — the
#     orchestrator's watchdog self-terminates the instant the lock disappears;
#   • OPENCLAW_PARENT_PID is this launcher; if the launcher itself is killed, the
#     watchdog sees the dead parent and self-terminates;
#   • on exit this launcher runs a TARGETED reap of exactly this run's process
#     group (never a blind pkill).
#
# Usage:
#   run-orchestrator.sh --single-book --slug <slug> [--source-json PATH]
#   run-orchestrator.sh            # full-batch mode
# Env overrides: OPENCLAW_RUN_ID, OPENCLAW_RUN_DIR, OPENCLAW_MAX_RUNTIME_SEC,
#                OPENCLAW_WATCHDOG_INTERVAL_SEC.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH="$SELF_DIR/orchestrator.py"
GUARD="$SELF_DIR/orphan_guard.py"
[ -f "$ORCH" ] || { echo "run-orchestrator: orchestrator.py not found at $ORCH" >&2; exit 1; }

RUN_ID="${OPENCLAW_RUN_ID:-book-$(date +%s)-$$}"
RUN_DIR="${OPENCLAW_RUN_DIR:-$HOME/.openclaw/pipeline-runs}"
mkdir -p "$RUN_DIR"
LOCK="$RUN_DIR/${RUN_ID}.live"
: > "$LOCK"                    # liveness lock — its removal aborts the run

cleanup() {
    rm -f "$LOCK" 2>/dev/null || true
    # TARGETED reap of exactly this run's process group (never a blind pkill).
    if [ -f "$GUARD" ]; then
        python3 "$GUARD" --run-dir "$RUN_DIR" --reap "$RUN_ID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM HUP

export OPENCLAW_RUN_ID="$RUN_ID"
export OPENCLAW_PARENT_PID="$$"
export OPENCLAW_RUN_LOCKFILE="$LOCK"
export OPENCLAW_RUN_DIR="$RUN_DIR"
export OPENCLAW_ORCH_DETACH=1

echo "run-orchestrator: run_id=$RUN_ID run_dir=$RUN_DIR (reapable; watchdog armed)"

# The orchestrator SELF-DETACHES into its own session/group via os.setsid()
# (OPENCLAW_ORCH_DETACH=1 -> orphan_guard.become_group_leader), so killing that
# recorded group reaps its whole child tree. No dependency on a `setsid` binary
# (absent on macOS). We WAIT on the child so this launcher stays the live parent
# its watchdog monitors; the trap fires if this launcher is signalled or exits.
python3 "$ORCH" "$@" &
CHILD=$!
wait "$CHILD"
