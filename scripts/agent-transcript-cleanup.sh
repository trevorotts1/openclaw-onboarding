#!/usr/bin/env bash
# agent-transcript-cleanup.sh - daily command-mode cron wrapper for agent-transcript-cleanup.py.
#
# agent-transcript-cleanup.py prunes old session windows (and every row that cascades from them)
# out of each agent's openclaw-agent.sqlite, archiving them first. See its header for the rules.
# Registered by scripts/ensure-pipeline-crons.sh as `agent-transcript-cleanup`, 04:30 daily
# America/New_York, COMMAND kind: no model, no delivery, never sends a chat message.
#
# EXIT CODES. 0 for everything that is not a crash: ran, nothing to do, locked, refused (a schema
# the script was not proven against is logged as REFUSED in the cleanup log and left alone). The
# scheduler counts a failing exit toward auto-disabling the job, and a refused night must never
# switch the cleanup off. Non-zero ONLY when the python itself crashed with an uncaught error.
# Run the python directly (not through this wrapper) when you need its real refusal exit code.

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

say() { printf '%s [agent-transcript-cleanup] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# OpenClaw root: explicit OPENCLAW_HOME / OC_ROOT, else VPS /data first, then the Mac home.
if [ -z "${OPENCLAW_HOME:-}" ]; then
  if [ -n "${OC_ROOT:-}" ]; then
    OPENCLAW_HOME="$OC_ROOT"
  elif [ -d /data/.openclaw ]; then
    OPENCLAW_HOME=/data/.openclaw
  elif [ -d "$HOME/.openclaw" ]; then
    OPENCLAW_HOME="$HOME/.openclaw"
  else
    say "SKIPPED: no OpenClaw root found; nothing to do"
    exit 0
  fi
fi
export OPENCLAW_HOME
export OPENCLAW_MAINTENANCE=1

command -v python3 >/dev/null 2>&1 || { say "SKIPPED: python3 not found"; exit 0; }
[ -f "$DIR/agent-transcript-cleanup.py" ] || { say "SKIPPED: $DIR/agent-transcript-cleanup.py not found (older bundle)"; exit 0; }

python3 -I "$DIR/agent-transcript-cleanup.py" "$@"
rc=$?
case "$rc" in
  0) ;;
  1) say "agent-transcript-cleanup.py reported an error on at least one database (rc=1); see $OPENCLAW_HOME/logs/agent-transcript-cleanup.log" ;;
  2) say "agent-transcript-cleanup.py refused at least one database (rc=2); see $OPENCLAW_HOME/logs/agent-transcript-cleanup.log" ;;
  *) say "CRASH: agent-transcript-cleanup.py exited rc=$rc"; exit "$rc" ;;
esac
exit 0
