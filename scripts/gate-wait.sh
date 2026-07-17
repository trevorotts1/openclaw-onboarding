#!/usr/bin/env bash
# gate-wait.sh — foreground, bounded gate-poll tool.
#
# ROOT CAUSE THIS FIXES (proved from the Claude Code 2.1.212 binary + a live
# transcript, not theory): an agent polling a CI/gate in a raw FOREGROUND loop
# outlasts Bash's 120s default timeout. The harness then AUTO-BACKGROUNDS the
# command ("moved to the background... you will be notified when it
# completes") — the agent never chose background. The harness's own system
# prompt then instructs the fatal wait ("do not poll" a background task). On
# stop, the harness reports "completed" to the parent carrying the "I'm
# waiting" text as the final result WHILE THE GATE IS STILL LIVE, and queued
# notifications for a stopped subagent reroute to the MAIN agent — the
# subagent that was actually waiting is never woken.
#
# THE FIX: bound the entire poll loop INSIDE one foreground command that is
# GUARANTEED to return well before the 120s auto-background threshold can
# fire — the new 90s default is intentionally BELOW that 120s threshold, so
# even a caller who invokes this script with the harness's own default Bash
# tool timeout (no explicit override) still gets a clean return, not an
# auto-background. Every inner poll (a `gh api` call, or the caller's `cmd`)
# is ALSO individually capped (see run_capped() below) so a single hung
# network/process call cannot itself push the whole script past its own
# --max-seconds deadline — the outer bound was previously the only bound,
# which was false advertising: an outer "guarantee" whose inner step has no
# timeout of its own is not a guarantee. Use a dedicated "still pending" exit
# code (2) so re-invoking this exact script is the obvious, safe, natural
# next move — no reliance on background notifications, ever.
#
# Usage:
#   gate-wait.sh ci <owner/repo> <sha> [--max-seconds N] [--interval N] [--call-timeout N]
#       Polls `gh api repos/<owner/repo>/commits/<sha>/check-runs --paginate`
#       from inside this one foreground command. Each individual `gh api`
#       call is capped at --call-timeout seconds (see run_capped()); a call
#       that exceeds it is treated as PENDING, not a failure, and the outer
#       loop continues.
#
#   gate-wait.sh cmd '<command>' --pass '<regex>' --fail '<regex>' [--max-seconds N] [--interval N] [--call-timeout N]
#       Generic form for any non-CI gate (a remote-log watch, a snapshot
#       smoke-test poll, etc.). Runs <command> repeatedly via `bash -lc`
#       (through run_capped(), so it can be killed cleanly on a per-call
#       timeout — plain `eval` cannot be interrupted from outside without
#       exiting the whole script), matches its combined stdout+stderr
#       against --fail first, then --pass (Python re.search,
#       case-insensitive, unanchored).
#
#       SECURITY NOTE: `cmd` mode executes the caller-supplied string as
#       shell code (via `bash -lc`, same trust boundary `eval` had — this
#       change is about killability, NOT sandboxing). This tool is for a
#       trusted operator/agent to poll a command THEY authored. Never wire
#       CHECK_CMD to unsanitized third-party/external input.
#
# Defaults:
#   --max-seconds  90   Hard wall-clock cap for the WHOLE script — kept
#                        BELOW the 120s harness auto-background threshold on
#                        purpose, so the safe behavior is the DEFAULT
#                        behavior, not something the caller has to remember
#                        to configure. Raise it only if you also explicitly
#                        raise the calling Bash tool's timeout to
#                        max-seconds + ~90s of margin — never let a
#                        caller-side timeout be shorter than max-seconds, or
#                        the harness's auto-background can still fire.
#   --interval     20   Seconds between polls.
#   --call-timeout 30   Per-inner-call cap (gh api, or the `cmd` command).
#                        Automatically clamped down to whatever time remains
#                        before --max-seconds, so no single inner call can
#                        push the script past its own deadline.
#
# Exit codes:
#   0  = gate is GREEN (all checks/pattern-matched success, zero failures)
#   1  = gate has a FAILURE present
#   2  = gate is still PENDING — call this script again (this is the
#        load-bearing exit code: it is what makes "run it again" the obvious
#        next move for an agent who never read the background-notification
#        warning at all). An inner call that times out also counts as
#        PENDING, never as a failure — a slow `gh api` is not a broken gate.
#   64 = usage / environment error (not a gate state — do not retry blindly)
#
# Every poll prints REAL PARTIAL STATE to stdout, e.g.:
#   [gate-wait 40s elapsed] 31 of 33 complete, 0 failures, pending: ['deploy-guard', 'e2e-smoke']
set -u

SCRIPT_NAME="gate-wait.sh"

print_usage() {
  cat <<'EOF'
gate-wait.sh — foreground, bounded gate-poll tool.

USAGE:
  gate-wait.sh ci <owner/repo> <sha> [--max-seconds N] [--interval N] [--call-timeout N]
  gate-wait.sh cmd '<command>' --pass '<regex>' --fail '<regex>' [--max-seconds N] [--interval N] [--call-timeout N]

DEFAULTS:
  --max-seconds  90   (guaranteed return before this many seconds; kept
                       below the 120s harness auto-background threshold)
  --interval     20   (seconds between polls)
  --call-timeout 30   (per-inner-call cap; clamped to remaining time)

EXIT CODES:
  0  gate is GREEN
  1  gate has a FAILURE present
  2  gate is still PENDING — call this script again
  64 usage / environment error
EOF
}

# run_capped SECONDS ARGV...
#   Runs ARGV (an argv vector, not a shell string) with a hard per-call
#   timeout enforced by python3's subprocess.run(timeout=...) — deliberately
#   NOT the GNU coreutils `timeout` command, which is not installed by
#   default on macOS/BSD userlands this script also needs to run on.
#   Prints the child's combined stdout+stderr. Exit code is the child's own
#   exit code, or 124 (matching GNU `timeout`'s convention) if it had to be
#   killed for exceeding SECONDS.
run_capped() {
  local cap="$1"; shift
  python3 - "$cap" "$@" <<'PYEOF'
import subprocess
import sys

cap = float(sys.argv[1])
cmd = sys.argv[2:]
try:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=cap,
    )
    sys.stdout.buffer.write(proc.stdout)
    sys.exit(proc.returncode)
except subprocess.TimeoutExpired as exc:
    if exc.stdout:
        sys.stdout.buffer.write(exc.stdout)
    sys.stdout.write("\n[run_capped] inner call exceeded {}s, killed\n".format(cap))
    sys.exit(124)
except FileNotFoundError as exc:
    sys.stderr.write("[run_capped] command not found: {}\n".format(exc))
    sys.exit(127)
PYEOF
}

if [ $# -eq 0 ]; then
  print_usage >&2
  exit 64
fi

MODE="$1"
shift

REPO=""
SHA=""
CHECK_CMD=""
PASS_PAT=""
FAIL_PAT=""
MAX_SECONDS=90
INTERVAL=20
CALL_TIMEOUT=30

case "$MODE" in
  ci)
    if [ $# -lt 2 ]; then
      echo "$SCRIPT_NAME: 'ci' requires <owner/repo> <sha>" >&2
      print_usage >&2
      exit 64
    fi
    REPO="$1"; SHA="$2"
    shift 2
    ;;
  cmd)
    if [ $# -lt 1 ]; then
      echo "$SCRIPT_NAME: 'cmd' requires a command string" >&2
      print_usage >&2
      exit 64
    fi
    CHECK_CMD="$1"
    shift
    ;;
  -h|--help)
    print_usage
    exit 0
    ;;
  *)
    echo "$SCRIPT_NAME: unknown mode '$MODE' (expected 'ci' or 'cmd')" >&2
    print_usage >&2
    exit 64
    ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --max-seconds)
      [ $# -ge 2 ] || { echo "$SCRIPT_NAME: --max-seconds needs a value" >&2; exit 64; }
      MAX_SECONDS="$2"; shift 2 ;;
    --interval)
      [ $# -ge 2 ] || { echo "$SCRIPT_NAME: --interval needs a value" >&2; exit 64; }
      INTERVAL="$2"; shift 2 ;;
    --call-timeout)
      [ $# -ge 2 ] || { echo "$SCRIPT_NAME: --call-timeout needs a value" >&2; exit 64; }
      CALL_TIMEOUT="$2"; shift 2 ;;
    --pass)
      [ $# -ge 2 ] || { echo "$SCRIPT_NAME: --pass needs a value" >&2; exit 64; }
      PASS_PAT="$2"; shift 2 ;;
    --fail)
      [ $# -ge 2 ] || { echo "$SCRIPT_NAME: --fail needs a value" >&2; exit 64; }
      FAIL_PAT="$2"; shift 2 ;;
    *)
      echo "$SCRIPT_NAME: unknown argument '$1'" >&2
      print_usage >&2
      exit 64 ;;
  esac
done

case "$MAX_SECONDS" in
  ''|*[!0-9]*) echo "$SCRIPT_NAME: --max-seconds must be a positive integer" >&2; exit 64 ;;
esac
case "$INTERVAL" in
  ''|*[!0-9]*) echo "$SCRIPT_NAME: --interval must be a positive integer" >&2; exit 64 ;;
esac
case "$CALL_TIMEOUT" in
  ''|*[!0-9]*) echo "$SCRIPT_NAME: --call-timeout must be a positive integer" >&2; exit 64 ;;
esac
if [ "$MAX_SECONDS" -eq 0 ] || [ "$INTERVAL" -eq 0 ] || [ "$CALL_TIMEOUT" -eq 0 ]; then
  echo "$SCRIPT_NAME: --max-seconds, --interval, and --call-timeout must all be > 0" >&2
  exit 64
fi
if [ "$MAX_SECONDS" -gt 570 ]; then
  echo "$SCRIPT_NAME: WARNING — --max-seconds ($MAX_SECONDS) is close to or over the 600s Bash tool ceiling; leaving little margin for latency. Recommended <= 480, default is 90." >&2
fi
if [ "$MAX_SECONDS" -gt 110 ]; then
  echo "$SCRIPT_NAME: NOTE — --max-seconds ($MAX_SECONDS) is above the 120s harness auto-background threshold this tool exists to stay under. Make sure the CALLING Bash tool timeout is explicitly raised to at least max-seconds + ~90s; do not rely on the harness's own default." >&2
fi

if [ "$MODE" = "ci" ]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "$SCRIPT_NAME: 'gh' CLI not found on PATH — this is an environment error, not a pending gate. Not retryable as-is." >&2
    exit 64
  fi
fi

if [ "$MODE" = "cmd" ]; then
  if [ -z "$PASS_PAT" ] || [ -z "$FAIL_PAT" ]; then
    echo "$SCRIPT_NAME: 'cmd' requires both --pass and --fail patterns" >&2
    exit 64
  fi
fi

START_TS=$(date +%s)
DEADLINE=$((START_TS + MAX_SECONDS))

while :; do
  NOW=$(date +%s)
  REMAIN=$((DEADLINE - NOW))
  if [ "$REMAIN" -le 0 ]; then
    printf '%s: max-seconds (%ds) reached, gate still PENDING. Call this script again (exit 2 by design).\n' "$SCRIPT_NAME" "$MAX_SECONDS"
    exit 2
  fi
  CALL_CAP=$CALL_TIMEOUT
  if [ "$REMAIN" -lt "$CALL_CAP" ]; then
    CALL_CAP=$REMAIN
  fi

  if [ "$MODE" = "ci" ]; then
    RAW_OUTPUT="$(run_capped "$CALL_CAP" gh api "repos/${REPO}/commits/${SHA}/check-runs" --paginate 2>&1)"
    CALL_RC=$?
    if [ "$CALL_RC" -eq 124 ]; then
      DECISION="PENDING|inner gh api call exceeded its ${CALL_CAP}s per-call cap (treated as pending, not a gate failure)"
    else
    DECISION="$(printf '%s' "$RAW_OUTPUT" | python3 -c '
import json, sys

data = sys.stdin.read()
dec = json.JSONDecoder()
idx = 0
runs_by_id = {}
parsed_any = False
while idx < len(data):
    while idx < len(data) and data[idx] in " \n\r\t":
        idx += 1
    if idx >= len(data):
        break
    try:
        obj, end = dec.raw_decode(data, idx)
    except ValueError:
        break
    idx = end
    parsed_any = True
    if isinstance(obj, dict) and "check_runs" in obj:
        for r in (obj.get("check_runs") or []):
            runs_by_id[r.get("id")] = r
    elif isinstance(obj, list):
        for r in obj:
            if isinstance(r, dict):
                runs_by_id[r.get("id")] = r

if not parsed_any:
    print("PENDING|gh api returned unparsable output (transient API error tolerated, not a gate failure); raw tail: " + data[-200:].replace("\n", " "))
    sys.exit(0)

runs = list(runs_by_id.values())
total = len(runs)
FAIL_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
completed = [r for r in runs if r.get("status") == "completed"]
failing = [r for r in completed if (r.get("conclusion") or "") in FAIL_CONCLUSIONS]
pending = [r for r in runs if r.get("status") != "completed"]
pending_names = [r.get("name") for r in pending]
failing_names = [r.get("name") for r in failing]

state = "{} of {} complete, {} failures, pending: {}".format(len(completed), total, len(failing), pending_names)
if failing:
    print("FAIL|" + state + " -- failing: " + str(failing_names))
elif total > 0 and len(completed) == total:
    print("GREEN|" + state)
else:
    print("PENDING|" + state)
')"
    fi
  else
    CMD_OUTPUT="$(run_capped "$CALL_CAP" bash -lc "$CHECK_CMD" 2>&1)"
    CALL_RC=$?
    if [ "$CALL_RC" -eq 124 ]; then
      DECISION="PENDING|inner check command exceeded its ${CALL_CAP}s per-call cap (treated as pending, not a gate failure/pass)"
    else
    DECISION="$(CMD_OUTPUT="$CMD_OUTPUT" PASS_PAT="$PASS_PAT" FAIL_PAT="$FAIL_PAT" python3 -c '
import os, re

output = os.environ.get("CMD_OUTPUT", "")
fail_pat = os.environ.get("FAIL_PAT", "")
pass_pat = os.environ.get("PASS_PAT", "")
tail = output[-300:].replace("\n", "\\n")

if fail_pat and re.search(fail_pat, output, re.IGNORECASE):
    print("FAIL|command output matched --fail " + repr(fail_pat) + "; tail: " + tail)
elif pass_pat and re.search(pass_pat, output, re.IGNORECASE):
    print("GREEN|command output matched --pass " + repr(pass_pat) + "; tail: " + tail)
else:
    print("PENDING|no --pass/--fail match yet; tail: " + tail)
')"
    fi
  fi

  STATUS="${DECISION%%|*}"
  STATE_LINE="${DECISION#*|}"
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TS))
  printf '[gate-wait %ds elapsed] %s\n' "$ELAPSED" "$STATE_LINE"

  case "$STATUS" in
    GREEN) exit 0 ;;
    FAIL) exit 1 ;;
  esac

  NOW=$(date +%s)
  if [ "$NOW" -ge "$DEADLINE" ]; then
    printf '%s: max-seconds (%ds) reached, gate still PENDING. Call this script again (exit 2 by design).\n' "$SCRIPT_NAME" "$MAX_SECONDS"
    exit 2
  fi

  REMAIN=$((DEADLINE - NOW))
  SLEEP_FOR=$INTERVAL
  if [ "$REMAIN" -lt "$SLEEP_FOR" ]; then
    SLEEP_FOR=$REMAIN
  fi
  if [ "$SLEEP_FOR" -gt 0 ]; then
    sleep "$SLEEP_FOR"
  fi
done
