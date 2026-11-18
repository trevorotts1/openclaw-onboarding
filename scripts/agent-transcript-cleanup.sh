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

# OpenClaw root. The python resolves it (OPENCLAW_STATE_DIR first, then OPENCLAW_HOME as either the
# .openclaw directory or its parent, then OC_ROOT, ~/.openclaw, /data/.openclaw) and says so out loud
# when it finds no agent databases. This wrapper only skips when nothing could possibly exist.
if [ -z "${OPENCLAW_STATE_DIR:-}${OPENCLAW_HOME:-}${OC_ROOT:-}" ] && [ ! -d /data/.openclaw ] && [ ! -d "$HOME/.openclaw" ]; then
  say "SKIPPED: no OpenClaw root found; nothing to do"
  exit 0
fi
export OPENCLAW_MAINTENANCE=1

command -v python3 >/dev/null 2>&1 || { say "SKIPPED: python3 not found"; exit 0; }
[ -f "$DIR/agent-transcript-cleanup.py" ] || { say "SKIPPED: $DIR/agent-transcript-cleanup.py not found (older bundle)"; exit 0; }

python3 -I "$DIR/agent-transcript-cleanup.py" "$@"
rc=$?
case "$rc" in
  0) ;;
  1) say "agent-transcript-cleanup.py reported an error on at least one database (rc=1); see agent-transcript-cleanup.log in the logs directory of the OpenClaw root" ;;
  2) say "agent-transcript-cleanup.py refused at least one database (rc=2); see agent-transcript-cleanup.log in the logs directory of the OpenClaw root" ;;
  *) say "CRASH: agent-transcript-cleanup.py exited rc=$rc"; exit "$rc" ;;
esac
exit 0
