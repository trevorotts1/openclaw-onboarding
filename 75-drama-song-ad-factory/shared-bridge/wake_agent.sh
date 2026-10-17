#!/usr/bin/env bash
# wake_agent.sh — one Drama Studio order, one agent turn, ONE delivery back to
# the client (U7).
#
#   shared-bridge/wake_agent.sh '<poll json line>'
#
# The argument is the single JSON line `studio_bridge.py poll` prints when an
# order is waiting:
#   {"order_id": "...", "run_dir": "...", "next": "python3 ... factory.py next ..."}
#
# It starts the agent with the command OpenClaw already documents for this —
# `openclaw agent --message` ("Run an agent turn via the Gateway"; see
# `openclaw agent --help`) — and passes `--deliver`, so the agent's reply goes
# back to the client's channel instead of stopping in the gateway
# (`--deliver` defaults to false). The message leads with the client's own
# words — the video has started, the approvals arrive here and on the studio
# page, with that page's actual URL when the box holds one — and then names the
# two things the agent must do: hand the client their personal studio link
# (INSTRUCTIONS.md step 6, `studio_bridge.py link`) and continue from `next`.
#
# The link comes from the bridge's OWN `link` command, not a second reader: a
# stored link prints with no request, a box with no key answers NO_KEY with an
# empty stdout, and a box with a key but no stored link mints one exactly as
# step 6 would. No link on stdout, no URL in the message.
#
# ONE wake, never a retry loop: this script runs once per claimed order. When
# delivery is impossible (no OpenClaw on PATH, or an OpenClaw too old to know
# `--deliver`) it says so on stderr and leaves 0 — a missing reply path must
# never fail the box's timer, which reports the POLL's own exit code anyway
# (timer-artifacts/run-timer.sh). A failed agent turn keeps that command's
# exit code: that is a real failure, not a missing delivery path.
#
# ROUTING: the rest of the skill sends with `--channel telegram`
# (intake_card.openclaw_send_argv). This asks the same gateway which agent that
# channel is bound to (`openclaw agents bindings`) and names it with `--agent`
# only when the answer is unambiguous — one agent on a box needs no name, and a
# genuinely ambiguous box is told to set DS_AGENT_ID rather than guessed at.
# DS_AGENT_ID always wins.
#
# OPENCLAW_BIN overrides the binary (tests point it at a recording stub).
# DS_CHANNEL overrides the channel (default: telegram, the skill's own).
set -u

BIN="${OPENCLAW_BIN:-openclaw}"
CHANNEL="${DS_CHANNEL:-telegram}"
# This script lives in shared-bridge, beside the bridge whose `link` it asks.
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "usage: wake_agent.sh '<poll json line>'" >&2
  exit 64
fi

PYTHON="$(command -v python3 2>/dev/null || true)"
[ -n "$PYTHON" ] || { echo "wake_agent: python3 not found" >&2; exit 69; }

# shellcheck disable=SC2016  # the python bodies are single-quoted on purpose:
# nothing in them may be expanded by this shell.
VALIDATE() {
  printf '%s' "$1" | "$PYTHON" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("wake_agent: poll line is not JSON", file=sys.stderr)
    sys.exit(65)
if not all(str(data.get(k) or "").strip()
           for k in ("order_id", "run_dir", "next")):
    print("wake_agent: poll line needs order_id, run_dir and next",
          file=sys.stderr)
    sys.exit(65)
'
}

# Bad input fails here, before anything on this box is touched.
VALIDATE "$1" || exit $?

# Delivery is a bonus the timer must never die on; the agent turn is not.
command -v "$BIN" >/dev/null 2>&1 || {
  echo "wake_agent: $BIN not on PATH; the agent cannot start and the client is not told" >&2
  exit 0
}

if "$BIN" agent --help 2>&1 | grep -q -- '--deliver'; then
  DELIVER_FLAG="--deliver"
else
  DELIVER_FLAG=""
  echo "wake_agent: this OpenClaw has no --deliver; the agent starts but the client is not told" >&2
fi

# The agent this box's channel is bound to, when that answer is unambiguous.
BOUND=""
[ -n "${DS_AGENT_ID:-}" ] || BOUND="$(printf '%s' "$("$BIN" agents bindings --json 2>/dev/null)" | "$PYTHON" -c '
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    sys.exit(0)          # no answer from the gateway: never guess, just name none
want = sys.argv[1]
hits = [r for r in rows
        if str((r.get("match") or {}).get("channel") or "") == want
        and r.get("agentId")]
ids = sorted({str(r.get("agentId")) for r in hits})
catch = sorted({str(r.get("agentId")) for r in hits
                if str((r.get("match") or {}).get("accountId") or "") == "*"})
if len(catch) == 1:
    print(catch[0])
elif len(ids) == 1:
    print(ids[0])
elif len(ids) > 1:
    print("wake_agent: %s binds more than one agent (%s); set DS_AGENT_ID "
          "to name one" % (want, ", ".join(ids)), file=sys.stderr)
' "$CHANNEL")" || true

# The client's personal studio link, through the bridge's own `link`: a stored
# link prints without asking the server, and a box with no key answers NO_KEY
# with an empty stdout. One line, or nothing.
LINK=""
LINK_OUT="$("$PYTHON" "$HERE/studio_bridge.py" link 2>/dev/null || true)"
case "$LINK_OUT" in
  https://*|http://*) LINK="$(printf '%s' "$LINK_OUT" | head -n 1)";;
esac

# The ONE message: what the client reads first, then the agent's instruction.
MSG="$(printf '%s' "$1" | LINK="$LINK" "$PYTHON" -c '
import json, os, sys
data = json.load(sys.stdin)
order_id = str(data.get("order_id") or "").strip()
next_cmd = str(data.get("next") or "").strip()
link = os.environ.get("LINK") or ""
where = ("It is on your Drama Studio page, at %s." % link) if link else \
        "It is on your Drama Studio page."
print("Your video has started. I am working on order %s now and I will bring "
      "you the script to approve first. %s Every approval for this video also "
      "reaches you right here in this chat. -- For the agent: hand the client "
      "their personal studio link now (INSTRUCTIONS.md step 6: `studio_bridge.py "
      "link`), then run skill 75 from `%s` to the first approval stop."
      % (order_id, where, next_cmd))
')" || exit $?

# One argv, one exec: agent id only when resolved, --deliver only when offered.
set -- agent
[ -n "${DS_AGENT_ID:-}" ] && set -- "$@" --agent "$DS_AGENT_ID"
[ -z "${BOUND:-}" ] || set -- "$@" --agent "$BOUND"
[ -z "$DELIVER_FLAG" ] || set -- "$@" --deliver
set -- "$@" --channel "$CHANNEL" --message "$MSG"

exec "$BIN" "$@"
