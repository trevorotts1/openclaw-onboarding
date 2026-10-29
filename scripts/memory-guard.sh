#!/usr/bin/env bash
# memory-guard.sh - nightly command-mode cron wrapper for memory-guard.py.
#
# memory-guard.py is the whole job (two deterministic checks, zero model calls):
#   1. key check  - tests the memory-search embedding key with OpenClaw's own
#                   probe; a dead key walks the backup chain (original provider,
#                   then OpenRouter nemotron, then Gemini); all dead = memory
#                   search off and the box's own bot asks the client to add funds.
#   2. idle check - a worker with no job or conversation in 30 days stops
#                   searching memory; it starts again when it is active.
# See the header of memory-guard.py for the full rules.
#
# Registered by scripts/ensure-pipeline-crons.sh as `memory-guard`, 02:15
# America/New_York (before the 03:00 dreaming run), COMMAND kind: no model, no
# delivery, so the cron itself can never message anyone. The only message this
# job can send is the guard's own Telegram notice to the client, and only when
# every option is dead.
#
# EXIT CODES. 0 for everything that is not a crash: ran, nothing to do, skipped,
# refused. The scheduler counts a failing exit toward auto-disabling the job, and a
# skipped night must never switch the guard off. Non-zero ONLY when memory-guard.py
# itself crashed (an uncaught error), so a real fault still shows up as a failed run.
#
# Runs as the box user. Refuses root: a root-owned openclaw.json freezes the gateway.

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

say() { printf '%s [memory-guard] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [ "$(id -u)" = "0" ]; then
  say "REFUSED: run as the box user, never root (a root-owned config freezes the gateway)"
  exit 0
fi

# OpenClaw root: explicit OC_ROOT, else VPS /data first, then the Mac home.
if [ -z "${OC_ROOT:-}" ]; then
  if [ -d /data/.openclaw ]; then
    OC_ROOT=/data/.openclaw
  elif [ -d "$HOME/.openclaw" ]; then
    OC_ROOT="$HOME/.openclaw"
  else
    say "SKIPPED: no OpenClaw root found; nothing to do"
    exit 0
  fi
fi
export OC_ROOT

command -v python3 >/dev/null 2>&1 || { say "SKIPPED: python3 not found"; exit 0; }
[ -f "$DIR/memory-guard.py" ] || { say "SKIPPED: $DIR/memory-guard.py not found (older bundle)"; exit 0; }

# A cron's environment can carry an unwritable TMPDIR; the openclaw CLI and python
# both need one. Fall back to a private directory under the OpenClaw root.
if [ ! -d "${TMPDIR:-/tmp}" ] || [ ! -w "${TMPDIR:-/tmp}" ]; then
  if mkdir -p "$OC_ROOT/memory-guard/tmp" 2>/dev/null && chmod 700 "$OC_ROOT/memory-guard" "$OC_ROOT/memory-guard/tmp" 2>/dev/null; then
    TMPDIR="$OC_ROOT/memory-guard/tmp"
    export TMPDIR
  fi
fi

python3 "$DIR/memory-guard.py" run
rc=$?
case "$rc" in
  0) ;;
  2) say "memory-guard.py refused or was misused (rc=2); see its output above" ;;
  *) say "CRASH: memory-guard.py exited rc=$rc"; exit "$rc" ;;
esac
exit 0
