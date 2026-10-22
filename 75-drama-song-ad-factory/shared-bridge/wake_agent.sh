#!/usr/bin/env bash
# wake_agent.sh — one Drama Studio order, one agent turn, ONE delivery back to
# the client (U7), with the durable wake record (U3, SPEC 9.4 / D35).
#
#   shared-bridge/wake_agent.sh '<poll json line>'
#
# The argument is the single JSON line `studio_bridge.py poll` prints when an
# order is waiting (or being re-woken):
#   {"order_id": "...", "run_dir": "...", "next": "python3 ... factory.py next ...",
#    "db": "<claim ledger path>"}
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
# step 6 would. No link on stdout, no URL in any diagnostic line — the link is
# capability-bearing and only the client's own message may carry it.
#
# DURABLE WAKE (D35). Before anything starts, the wake is recorded
# (`studio_bridge.py wake --queued`) on the claim ledger: a concurrent wake for
# the same order is refused, so a turn is never started twice. On success the
# ledger records `wake --ack` (execution-accepted) and the order's later polls
# stay silent. On any failure the ledger records `wake --fail` with a NAMED
# reason and the request STAYS queued — the next poll re-emits the line and the
# wake is retried under the same order. A failure is never converted into
# silent success: every path below exits with what actually happened.
#
# ROUTING: the rest of the skill sends with `--channel telegram`
# (intake_card.openclaw_send_argv). This asks the same gateway which agent that
# channel is bound to (`openclaw agents bindings`) and names it with `--agent`
# only when the answer is unambiguous — one resolved agent needs no guessing,
# and a genuinely ambiguous box is told to set DS_AGENT_ID rather than started
# as an UNNAMED DEFAULT AGENT (SPEC 9.4: never). DS_AGENT_ID always wins.
#
# EXIT (the timer propagates a wake failure separately from the poll's own):
#   0   the agent turn was accepted AND the reply path is supported
#   64  usage · 65 bad poll line · 69 python3 missing
#   70  the wake did not happen (no OpenClaw, ambiguous/missing agent binding)
#   71  the turn ran but the client cannot be told (no --deliver on this
#       runtime) — work continues, the gap is named, not hidden
#   else  the agent turn's own exit code (turn failed; wake stays queued)
#
# OPENCLAW_BIN overrides the binary (tests point it at a recording stub).
# DS_CHANNEL overrides the channel (default: telegram, the skill's own).
set -u

BIN="${OPENCLAW_BIN:-openclaw}"
CHANNEL="${DS_CHANNEL:-telegram}"
# This script lives in shared-bridge, beside the bridge whose `link` it asks.
HERE="$(cd "$(dirname "$0")" && pwd)"

# The two exit codes that mean "the wake did not complete": the timer surfaces
# them; the ledger keeps the request queued for the retry.
EXIT_NO_WAKE=70
EXIT_NO_DELIVERY=71

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

# The order id and the claim ledger the poll recorded this order on.
ORDER_ID="$(printf '%s' "$1" | "$PYTHON" -c '
import json, sys
print(str(json.load(sys.stdin).get("order_id") or "").strip())
')"
DB="$(printf '%s' "$1" | "$PYTHON" -c '
import json, sys
print(str(json.load(sys.stdin).get("db") or "").strip())
')"

# The durable wake record. Best-effort bookkeeping: a broken ledger must not
# eat a real agent turn, but every outcome is attempted. `--queued` answers
# "in_flight" when another wake already holds this order — that is a quiet
# success (the request is active), never a duplicate turn.
WAKE_LEDGER() {
  if [ -n "$DB" ]; then
    "$PYTHON" "$HERE/studio_bridge.py" wake "$@" --order "$ORDER_ID" --db "$DB"
  else
    "$PYTHON" "$HERE/studio_bridge.py" wake "$@" --order "$ORDER_ID"
  fi
}

QUEUED="$(WAKE_LEDGER --queued 2>/dev/null || true)"
case "$QUEUED" in
  *'"in_flight": true'*) exit 0 ;;   # a wake is already running: quiet success
esac

FAIL_AND_EXIT() {  # <ledger reason> <exit code> <message>
  WAKE_LEDGER --fail --reason "$1" >/dev/null 2>&1 || true
  echo "wake_agent: $3" >&2
  exit "$2"
}

# Delivery is a bonus the turn can run without — but it is never a silent one.
command -v "$BIN" >/dev/null 2>&1 || FAIL_AND_EXIT NO_CLI "$EXIT_NO_WAKE" \
  "$BIN not on PATH; the agent cannot start and the client is not told (wake stays queued)"

if "$BIN" agent --help 2>&1 | grep -q -- '--deliver'; then
  DELIVER_FLAG="--deliver"
else
  DELIVER_FLAG=""
  NO_DELIVERY=1
fi

# The agent this box's channel is bound to — resolved, never guessed. An
# ambiguous or empty answer stops the wake with an actionable message instead
# of starting an unnamed default agent (SPEC 9.4).
BOUND=""
if [ -n "${DS_AGENT_ID:-}" ]; then
  BOUND="$DS_AGENT_ID"
else
  BINDINGS="$("$BIN" agents bindings --json 2>/dev/null || true)"
  RESOLVED="$(printf '%s' "$BINDINGS" | "$PYTHON" -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    print("UNRESOLVED")            # gateway did not answer: cannot prove one agent
    sys.exit(0)
try:
    rows = json.loads(raw)
except Exception:
    print("UNRESOLVED")
    sys.exit(0)
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
    print("AMBIGUOUS:" + ",".join(ids))
else:
    print("NONE")
' "$CHANNEL")" || RESOLVED="UNRESOLVED"
  case "$RESOLVED" in
    AMBIGUOUS:*) FAIL_AND_EXIT AMBIGUOUS_BINDING "$EXIT_NO_WAKE" \
      "$CHANNEL binds more than one agent (${RESOLVED#AMBIGUOUS:}); set DS_AGENT_ID to name one (wake stays queued)" ;;
    NONE) FAIL_AND_EXIT NO_BINDING "$EXIT_NO_WAKE" \
      "no agent is bound to channel '$CHANNEL'; set DS_AGENT_ID (wake stays queued)" ;;
    UNRESOLVED) FAIL_AND_EXIT BINDINGS_UNAVAILABLE "$EXIT_NO_WAKE" \
      "cannot resolve the agent binding (gateway not answering); set DS_AGENT_ID (wake stays queued)" ;;
    *) BOUND="$RESOLVED" ;;
  esac
fi

# The client's personal studio link, through the bridge's own `link`: a stored
# link prints without asking the server, and a box with no key answers NO_KEY
# with an empty stdout. One line, or nothing. Never a diagnostic line.
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

# One argv, one invocation: the resolved agent id, --deliver only when offered.
set -- agent
[ -n "${BOUND:-}" ] && set -- "$@" --agent "$BOUND"
[ -z "${DELIVER_FLAG:-}" ] || set -- "$@" "$DELIVER_FLAG"
set -- "$@" --channel "$CHANNEL" --message "$MSG"

"$BIN" "$@"
RC=$?

if [ "$RC" -eq 0 ]; then
  # The supported runtime acknowledged the turn: execution-accepted, and the
  # order's later polls stay silent (no duplicate campaign or paid job).
  WAKE_LEDGER --ack >/dev/null 2>&1 || true
  if [ -n "${NO_DELIVERY:-}" ]; then
    echo "wake_agent: this OpenClaw has no --deliver; the agent turn ran but the client is not told (recorded)" >&2
    exit "$EXIT_NO_DELIVERY"
  fi
  exit 0
fi

# The turn failed: named, recorded, and still queued for the next poll's retry.
WAKE_LEDGER --fail --reason AGENT_TURN_FAILED >/dev/null 2>&1 || true
exit "$RC"
