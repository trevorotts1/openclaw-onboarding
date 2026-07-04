#!/usr/bin/env bash
# reap-orchestrators.sh — TARGETED reaper for book-to-persona orchestrator runs.
#
# Kills exactly a run's process GROUP (recorded in its pidfile), NEVER a blind
# `pkill python` that could hit an unrelated run. Two modes:
#
#   reap-orchestrators.sh --sweep         # reap every run whose PARENT is dead
#   reap-orchestrators.sh --run RUN_ID    # reap exactly this run
#
# --sweep is the safe cron/stop-hook payload: it only touches runs whose
# launching coordinator is already gone (orphans). Env: OPENCLAW_RUN_DIR
# (default ~/.openclaw/pipeline-runs).
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$SELF_DIR/orphan_guard.py"
RUN_DIR="${OPENCLAW_RUN_DIR:-$HOME/.openclaw/pipeline-runs}"
[ -f "$GUARD" ] || { echo "reap-orchestrators: orphan_guard.py not found at $GUARD" >&2; exit 1; }

case "${1:-}" in
    --sweep)
        exec python3 "$GUARD" --run-dir "$RUN_DIR" --sweep ;;
    --run)
        [ -n "${2:-}" ] || { echo "usage: reap-orchestrators.sh --run RUN_ID" >&2; exit 2; }
        exec python3 "$GUARD" --run-dir "$RUN_DIR" --reap "$2" ;;
    *)
        echo "usage: reap-orchestrators.sh --sweep | --run RUN_ID" >&2
        exit 2 ;;
esac
