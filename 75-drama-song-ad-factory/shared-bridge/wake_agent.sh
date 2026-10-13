#!/usr/bin/env bash
# wake_agent.sh — one Drama Studio order, one agent turn (U7).
#
#   shared-bridge/wake_agent.sh '<poll json line>'
#
# The argument is the single JSON line `studio_bridge.py poll` prints when an
# order is waiting:
#   {"order_id": "...", "run_dir": "...", "next": "python3 ... factory.py next ..."}
#
# It starts the agent with the command OpenClaw already documents for this —
# `openclaw agent --message` ("Run an agent turn via the Gateway"; see
# `openclaw agent --help`). No new mechanism, no interactive shell, no reply
# delivery: the agent reads the instruction and runs skill 75 itself.
#
# OPENCLAW_BIN overrides the binary (tests point it at a recording stub).
set -u

BIN="${OPENCLAW_BIN:-openclaw}"

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "usage: wake_agent.sh '<poll json line>'" >&2
  exit 64
fi

command -v python3 >/dev/null 2>&1 || { echo "wake_agent: python3 not found" >&2; exit 69; }

# shellcheck disable=SC2016  # the python body is single-quoted on purpose:
# nothing in it may be expanded by this shell.
MSG="$(printf '%s' "$1" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("wake_agent: poll line is not JSON", file=sys.stderr)
    sys.exit(65)
order_id = str(data.get("order_id") or "").strip()
run_dir = str(data.get("run_dir") or "").strip()
next_cmd = str(data.get("next") or "").strip()
if not (order_id and run_dir and next_cmd):
    print("wake_agent: poll line needs order_id, run_dir and next",
          file=sys.stderr)
    sys.exit(65)
print("A Drama Studio order is ready: order %s, run dir %s. Run skill 75 "
      "from `%s` to the first approval stop. Approvals for this run also "
      "publish to the studio page." % (order_id, run_dir, next_cmd))
')" || exit $?

exec "$BIN" agent --message "$MSG"
