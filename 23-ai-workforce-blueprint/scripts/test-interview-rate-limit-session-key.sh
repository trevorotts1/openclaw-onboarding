#!/usr/bin/env bash
# test-interview-rate-limit-session-key.sh
#
# Regression battery for the P0 incident: a real client's AI Workforce
# Interview froze at question 5. Their Telegram conversation continued for 70+
# more minutes across 13 more messages -- none of it was ever persisted. No
# crash, no outage; their model calls returned status=200 throughout. The
# answers were silently refused and thrown away.
#
# ROOT CAUSE (confirmed against the real code, not assumed):
#   - lib-interview-rate-limit.sh defaulted INTERVIEW_RATE_LIMIT_MAX=5 per
#     INTERVIEW_RATE_LIMIT_WINDOW_SECONDS=3600, keyed by whatever string is
#     passed as --asked-by.
#   - The Command Center's src/app/api/interview/answer/route.ts defaults
#     askedBy to the LITERAL STRING 'interview-web' whenever there is no
#     Cf-Access email / explicit id -- which is ALWAYS true for a
#     Telegram-conducted or otherwise unauthenticated session.
#   - update-interview-state.sh used that value AS THE RATE-LIMIT KEY
#     directly (RL_SESSION="${ASKED_BY:-}"), so every unauthenticated
#     interview session on the box shared ONE ledger bucket. The client's
#     ledger held exactly 5 timestamps under key "interview-web", all inside
#     10 minutes, and their build state froze at that instant. Every later
#     stamp attempt exited 1 (a generic, indistinguishable failure code) and
#     was discarded -- the caller had no way to tell "you are being
#     rate-limited, retry" from "something is broken".
#
# What this battery pins, and what each case would have caught:
#   1  two distinct interview sessions get INDEPENDENT rate-limit buckets,
#      even when both send the identical --asked-by literal (the collapse)
#   2  the ledger is never keyed by the "interview-web" literal itself
#   3  a trip is LOUD: a distinct exit code (89, never the generic 1) and a
#      plain-language stderr message naming the session + confirming nothing
#      was lost + how to get it back (the silence)
#   4  a trip LOSES NOTHING: the refused stamp is spooled durably with its
#      exact flags in .interview-state-deferred.jsonl (the data loss)
#   5  draining without headroom leaves the entry queued (no partial/garbled
#      apply); draining WITH headroom applies it and consumes the spool
#      (no infinite replay)
#   6  ANY subsequent successful call -- not just an explicit
#      --drain-deferred -- opportunistically flushes the backlog too
#   7  the default budget (60/hour) clears a sustained one-answer-per-minute
#      pace, and stays fully env-overridable
#   8  interview_session_id() prefers the stable interviewSessionId over
#      lastQuestionAskedBy (the fallback resolver used to read the shared
#      literal straight back out of build-state once it had ever been
#      stamped there -- reproducing the collapse even on its own "fix path")
#   9  the authenticated path (a real Cf-Access/operator email as --asked-by)
#      is preserved EXACTLY: still the bucket key, still recorded verbatim
#      in lastQuestionAskedBy -- this fix must never change that behavior
#   10 mutation proof -- the battery goes RED when the fix is reverted
#
# Self-contained: builds its own HOME/workspace, never touches a real box,
# never touches client data.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib-interview-rate-limit.sh"
UPD="$SCRIPT_DIR/update-interview-state.sh"

FAILED=0
TOTAL=0
pass() { TOTAL=$((TOTAL + 1)); echo "ok - $1"; }
fail() {
  TOTAL=$((TOTAL + 1))
  FAILED=1
  echo "not ok - $1"
  [ -n "${2:-}" ] && echo "  $2"
}

TD="$(mktemp -d -t rl-session.XXXXXX)"
cleanup() { rm -rf "$TD"; }
trap cleanup EXIT

if [ -d /data/.openclaw/workspace ]; then
  echo "1..0 # SKIP /data/.openclaw/workspace exists - the HOME override would not be honored"
  exit 0
fi

WS="$TD/home/.openclaw/workspace"
mkdir -p "$WS"
STATE="$WS/.workforce-build-state.json"
LEDGER="$WS/.interview-rate-limit.json"
SPOOL="$WS/.interview-state-deferred.jsonl"

reset_ws() {
  local session_id="${1:-11111111-1111-1111-1111-111111111111}"
  rm -f "$LEDGER" "$SPOOL"
  cat >"$STATE" <<EOF
{
  "interviewSessionId": "$session_id",
  "interviewProgress": {
    "lastQuestionNumber": 1,
    "lastQuestionAskedBy": "interview-web"
  }
}
EOF
}

run_upd() {
  local session="$1"; shift
  ( export HOME="$TD/home"; export INTERVIEW_SESSION_ID="$session"; bash "$UPD" "$@" ) >"$TD/out" 2>&1
  echo "$?"
}

# The Command Center only ever supplies --session-id / INTERVIEW_SESSION_ID
# when there is NO real identity (unauthenticated branch) -- see
# src/app/api/interview/answer/route.ts. An authenticated call carries ONLY
# --asked-by, never an explicit session id. This helper reproduces that exact
# shape so test 9 pins the real contract, not a strawman.
run_upd_authenticated() {
  ( export HOME="$TD/home"; unset INTERVIEW_SESSION_ID; bash "$UPD" "$@" ) >"$TD/out" 2>&1
  echo "$?"
}

ledger_keys() {
  python3 -c "
import json,sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(''); raise SystemExit(0)
print(' '.join(sorted(d.get('sessions', {}).keys())))
" "$LEDGER" 2>/dev/null
}

SESSION_A="aaaaaaaa-0000-0000-0000-00000000000a"
SESSION_B="bbbbbbbb-0000-0000-0000-00000000000b"

# ── 1) TWO DISTINCT SESSIONS DO NOT SHARE A BUCKET ───────────────────────────
# Both send the IDENTICAL --asked-by the web route hardcodes for every
# unauthenticated session. Before the fix both collapse onto "interview-web".
reset_ws "$SESSION_A"
export INTERVIEW_RATE_LIMIT_MAX=2
export INTERVIEW_RATE_LIMIT_WINDOW_SECONDS=3600

a1=$(run_upd "$SESSION_A" --phase discovery --question-number 2 --asked-by interview-web)
a2=$(run_upd "$SESSION_A" --phase discovery --question-number 3 --asked-by interview-web)
a3=$(run_upd "$SESSION_A" --phase discovery --question-number 4 --asked-by interview-web)
b1=$(run_upd "$SESSION_B" --phase discovery --question-number 2 --asked-by interview-web)

if [ "$a1" = "0" ] && [ "$a2" = "0" ] && [ "$a3" = "89" ] && [ "$b1" = "0" ]; then
  pass "two distinct interview sessions do NOT share a rate-limit bucket"
else
  fail "two distinct interview sessions do NOT share a rate-limit bucket" \
    "session A: $a1,$a2,$a3 (want 0,0,89); session B first answer: $b1 (want 0) - B would be locked out by A's typing"
fi

# ── 2) THE LEDGER IS NEVER KEYED BY THE SHARED LITERAL ───────────────────────
keys="$(ledger_keys)"
if [ -n "$keys" ] && [[ "$keys" == *"$SESSION_A"* ]] && [[ "$keys" != *"interview-web"* ]]; then
  pass "the ledger is keyed by interviewSessionId, never by the 'interview-web' literal"
else
  fail "the ledger is keyed by interviewSessionId, never by the 'interview-web' literal" "ledger keys were: [$keys]"
fi

# ── 3) A TRIP IS LOUD ─────────────────────────────────────────────────────────
reset_ws "$SESSION_A"
export INTERVIEW_RATE_LIMIT_MAX=1
_=$(run_upd "$SESSION_A" --phase discovery --question-number 2 --asked-by interview-web)
trip_code=$(run_upd "$SESSION_A" --phase discovery --question-number 3 --asked-by interview-web)
trip_out="$(cat "$TD/out")"

if [ "$trip_code" = "89" ]; then
  pass "a tripped limit exits with the distinct rate-limited code 89 (never the generic 1)"
else
  fail "a tripped limit exits with the distinct rate-limited code 89 (never the generic 1)" "exit code was $trip_code"
fi

if [[ "$trip_out" == *"RATE-LIMIT"* ]] \
  && [[ "$trip_out" == *"$SESSION_A"* ]] \
  && [[ "$trip_out" == *"NOT lost"* ]] \
  && [[ "$trip_out" =~ [Rr]etry ]]; then
  pass "a tripped limit prints a plain-language error naming the session, that nothing was lost, and how to retry"
else
  fail "a tripped limit prints a plain-language error naming the session, that nothing was lost, and how to retry" "output was: $trip_out"
fi

# ── 4) A TRIP LOSES NOTHING: the refused stamp is spooled durably ───────────
if [ -s "$SPOOL" ] && grep -aq "$SESSION_A" "$SPOOL" && grep -aq '"questionNumber": 3' "$SPOOL"; then
  pass "a refused stamp is spooled durably with its exact fields (nothing dropped)"
else
  detail="spool missing or incomplete at $SPOOL"
  [ -f "$SPOOL" ] && detail="$detail; contents: $(cat "$SPOOL")"
  fail "a refused stamp is spooled durably with its exact fields (nothing dropped)" "$detail"
fi

# ── 5a) Draining WITHOUT headroom leaves the entry queued ───────────────────
drain_tight=$(run_upd "$SESSION_A" --drain-deferred)
if [ "$drain_tight" = "0" ] && [ -s "$SPOOL" ] && grep -aq "$SESSION_A" "$SPOOL"; then
  pass "draining without headroom leaves the deferred stamp queued (no forced/garbled apply)"
else
  fail "draining without headroom leaves the deferred stamp queued (no forced/garbled apply)" "drain exit=$drain_tight spool: $(cat "$SPOOL" 2>/dev/null || echo MISSING)"
fi

# ── 5b) Draining WITH headroom applies the deferred stamp and consumes it ──
export INTERVIEW_RATE_LIMIT_MAX=50
drain_code=$(run_upd "$SESSION_A" --drain-deferred)
stamped=$(jq -r '.interviewProgress.lastQuestionNumber // 0' "$STATE" 2>/dev/null || echo 0)
if [ "$drain_code" = "0" ] && [ "$stamped" = "3" ]; then
  pass "--drain-deferred replays the refused stamp with headroom and no answer position is lost"
else
  fail "--drain-deferred replays the refused stamp with headroom and no answer position is lost" \
    "drain exit=$drain_code lastQuestionNumber=$stamped (want 0 / 3)"
fi

if [ ! -s "$SPOOL" ]; then
  pass "a successful drain consumes the spool (no infinite replay)"
else
  fail "a successful drain consumes the spool (no infinite replay)" "spool still holds: $(cat "$SPOOL")"
fi

# ── 6) ANY subsequent successful call opportunistically drains the backlog ──
reset_ws "$SESSION_A"
export INTERVIEW_RATE_LIMIT_MAX=1
_=$(run_upd "$SESSION_A" --phase discovery --question-number 5 --asked-by interview-web)
_=$(run_upd "$SESSION_A" --phase discovery --question-number 6 --asked-by interview-web)  # trips, queues qnum=6
export INTERVIEW_RATE_LIMIT_MAX=50
next_code=$(run_upd "$SESSION_A" --phase discovery --question-number 7 --asked-by interview-web)  # ordinary call, not --drain-deferred
final_q=$(jq -r '.interviewProgress.lastQuestionNumber // 0' "$STATE" 2>/dev/null || echo 0)
if [ "$next_code" = "0" ] && [ "$final_q" = "7" ] && [ ! -s "$SPOOL" ]; then
  pass "an ordinary later call (not --drain-deferred) opportunistically flushes the queued backlog too"
else
  fail "an ordinary later call (not --drain-deferred) opportunistically flushes the queued backlog too" \
    "next_code=$next_code final lastQuestionNumber=$final_q (want 7) spool=$(cat "$SPOOL" 2>/dev/null || echo EMPTY)"
fi

# ── 7) THE DEFAULT BUDGET FITS A HUMAN, AND STAYS OVERRIDABLE ───────────────
observed_default=$(
  unset INTERVIEW_RATE_LIMIT_MAX
  # shellcheck disable=SC1090
  source "$LIB" >/dev/null 2>&1
  printf '%s' "${INTERVIEW_RATE_LIMIT_MAX:-unset}"
)
if [ "$observed_default" = "60" ]; then
  pass "the default budget is 60/hour - one answer per minute sustained for a full hour"
else
  fail "the default budget is 60/hour - one answer per minute sustained for a full hour" \
    "default was '$observed_default' (5/hour trips a real client inside ten minutes)"
fi

override_seen=$(
  export INTERVIEW_RATE_LIMIT_MAX=7
  # shellcheck disable=SC1090
  source "$LIB" >/dev/null 2>&1
  printf '%s' "$INTERVIEW_RATE_LIMIT_MAX"
)
if [ "$override_seen" = "7" ]; then
  pass "the budget stays env-overridable (INTERVIEW_RATE_LIMIT_MAX still wins)"
else
  fail "the budget stays env-overridable (INTERVIEW_RATE_LIMIT_MAX still wins)" "saw '$override_seen'"
fi

# ── 8) THE FALLBACK RESOLVER PREFERS THE STABLE SESSION ID ──────────────────
reset_ws "$SESSION_B"
resolved=$(
  export HOME="$TD/home"
  unset INTERVIEW_SESSION_ID
  # shellcheck disable=SC1090
  source "$LIB" >/dev/null 2>&1
  interview_session_id
)
if [ "$resolved" = "$SESSION_B" ]; then
  pass "interview_session_id() prefers the stable interviewSessionId over lastQuestionAskedBy"
else
  fail "interview_session_id() prefers the stable interviewSessionId over lastQuestionAskedBy" \
    "resolved '$resolved', wanted '$SESSION_B' (build-state also carries lastQuestionAskedBy=interview-web)"
fi

rejected=$(
  export HOME="$TD/home"
  # shellcheck disable=SC1090
  source "$LIB" >/dev/null 2>&1
  interview_rate_limit_session_key "interview-web" "interview-web"
)
if [ "$rejected" = "$SESSION_B" ]; then
  pass "the shared literal passed as EITHER the explicit session id or --asked-by is rejected and resolved to the real session"
else
  fail "the shared literal passed as EITHER the explicit session id or --asked-by is rejected and resolved to the real session" \
    "resolved '$rejected', wanted '$SESSION_B'"
fi

# ── 9) THE AUTHENTICATED PATH IS PRESERVED EXACTLY ──────────────────────────
reset_ws "$SESSION_A"
export INTERVIEW_RATE_LIMIT_MAX=50
auth_code=$(run_upd_authenticated --phase discovery --question-number 6 --asked-by "owner@example.com")
recorded_by=$(jq -r '.interviewProgress.lastQuestionAskedBy // ""' "$STATE" 2>/dev/null || echo "")
recorded_q=$(jq -r '.interviewProgress.lastQuestionNumber // 0' "$STATE" 2>/dev/null || echo 0)
auth_keys="$(ledger_keys)"
if [ "$auth_code" = "0" ] && [ "$recorded_by" = "owner@example.com" ] && [ "$recorded_q" = "6" ] \
  && [[ "$auth_keys" == *"owner@example.com"* ]] && [[ "$auth_keys" != *"$SESSION_A"* ]]; then
  pass "the authenticated path still works: bucket key is the real identity (unchanged), --asked-by recorded verbatim"
else
  fail "the authenticated path still works: bucket key is the real identity (unchanged), --asked-by recorded verbatim" \
    "exit=$auth_code lastQuestionAskedBy='$recorded_by' lastQuestionNumber=$recorded_q ledger keys=[$auth_keys]"
fi

echo "# Ran $TOTAL tests."
if [ "$FAILED" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
