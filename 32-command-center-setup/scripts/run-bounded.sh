#!/usr/bin/env bash
# run-bounded.sh SECONDS command [args...]
# Runs the command with stdin from /dev/null and a hard wall-clock limit.
# Portable on macOS (no GNU timeout needed): perl alarm survives exec, so the
# command is killed by SIGALRM (exit 142) if it outlives the limit. A hung
# helper (e.g. the CC contract check that printed OK and never exited, 39 min
# on one Mac) can therefore never wedge the installer or updater.
secs="${1:?seconds}"; shift
if command -v perl >/dev/null 2>&1; then
  exec perl -e 'alarm shift; exec @ARGV or exit 127' "$secs" "$@" </dev/null
fi
# ponytail: no perl (never seen on Mac/Linux boxes) -> unbounded but stdin-closed.
exec "$@" </dev/null
