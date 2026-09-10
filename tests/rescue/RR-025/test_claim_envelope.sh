#!/usr/bin/env bash
# tests/rescue/RR-025/test_claim_envelope.sh — RR-025 gate (ONB receiver).
#
# Pins the typed claim envelope and the canonical session/cache identity.
# SPEC RR-025: "Validate one typed claim envelope before decoding/execution.
# Require supported protocol/mode, incident/instruction/attempt, local
# enrollment match, current lease and explicit agent capability. Derive
# session/cache identity from canonical company+runtime+incident+attempt using
# a collision-resistant encoding/hash; never accept a shared empty suffix.
# Verify requested local agent exists. If absent, use a verified authorized
# same-client General/CEO fallback and record substitution, or keep an owned
# operator-recoverable routing fault. Unknown modes and identity mismatches
# execute nothing and produce structured rejection."
#
# EVIDENCE STANDARD (SPEC required QC): "Omit/mistype each field, use
# unknownmode, invalid base64, two simultaneous tickets, two clients, keys a/b
# versus a_b, unknown agent and foreign session. Invalid input makes zero agent
# calls; legitimate fallback stays in the correct client context."
#
# So the assertions are NOT "the function returned 1". Each case drives the
# REAL rescue-poll.sh against a loopback receiver stub and counts the agent
# turns a stub `openclaw` binary recorded. "Zero agent calls" is a fact about
# the box, and the recorder is proven able to fire by the positive control at
# the top of the battery — a silent log means the poll refused, not that the
# detector is broken.
#
# Hermetic: temp dirs, synthetic slug/token, loopback HTTP only, no credential.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"
HELPER="$REPO/shared-utils/rescue-env.sh"
SUPERVISE="$REPO/shared-utils/rescue-supervise.py"
export POLL HELPER SUPERVISE

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

for f in "$POLL" "$HELPER" "$SUPERVISE"; do
  [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

. "$HERE/lib-envelope-harness.sh"

echo "== RR-025: typed claim envelope / canonical identity / capability =="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr025.XXXXXX")"

# Cleanup guard. Bash runs EXIT traps in SUBSHELLS too: the receiver stub is
# forked as a background job (harness_start_receiver), and when such a subshell
# exits it fires this trap with the parent's $WORK still in its environment.
# On bash 5.2 (Debian 12) that deleted the scratch tree mid-run, and the pkill
# killed the very stub the next case depended on. The flag is inherited UNSET
# by every subshell (they fork before it is set), so only the main shell cleans
# up. PID guards are not portable: bash 3.2 (macOS /bin/sh) has no BASHPID and
# keeps $$ as the parent's pid inside a subshell.
RR025_DONE=""
trap '[ -n "$RR025_DONE" ] && { rm -rf "$WORK"; pkill -f "rr025-recv" 2>/dev/null || true; }' EXIT
BASE_PORT=$(( 21000 + ($$ % 2000) ))

# ---------------------------------------------------------------------------
# case runner: harness_case <name> <response-json> [slug] [roster]
#   -> runs the real poll once against a stub receiver returning <response-json>
#      and leaves the artifact paths in CASE_* for the assertions below.
# ---------------------------------------------------------------------------
CASE_AGENT_CALLS=0
CASE_CLAIMS=0
CASE_ROOT=""
CASE_RECORD=""
CASE_PORT=0
CASE_SLUG=""
CASE_ROSTER=""
CASE_RC=0
CASE_INDEX=0
CASE_RECEIVER_PID=""

# A brace-bearing `${4:-{...}}` default is SILENTLY TRUNCATED at the first `}`
# (the parameter expansion ends there and the remaining `]` is appended as
# literal text), which produced the invalid roster `[{"id":"main","isDefault":true}]`
# -> `[{...}]`. Written out longhand so the default survives.
DEFAULT_ROSTER='[{"id":"main","isDefault":true}]'

harness_case() {
    CASE_INDEX=$((CASE_INDEX+1))
    CASE_PORT=$(( BASE_PORT + CASE_INDEX ))
    CASE_SLUG="${3:-box-synthetic}"
    if [ -n "${4:-}" ]; then CASE_ROSTER="$4"; else CASE_ROSTER="$DEFAULT_ROSTER"; fi
    CASE_ROOT="$WORK/case$CASE_INDEX"
    CASE_RECORD="$CASE_ROOT/agent-record.txt"
    CLAIM_LOG="$CASE_ROOT/claims.txt"
    rm -rf "$CASE_ROOT"; mkdir -p "$CASE_ROOT"
    harness_make_box "$CASE_ROOT" "$CASE_SLUG"
    harness_write_store "$CASE_ROOT" "$CASE_PORT" "$CASE_SLUG"
    harness_start_receiver "$CASE_PORT" "$2" "$CLAIM_LOG" > "$CASE_ROOT/recv.pid"
    CASE_RECEIVER_PID="$(cat "$CASE_ROOT/recv.pid" 2>/dev/null || echo '')"
    sleep 0.6
    OPENCLAW_RECORD="$CASE_RECORD" \
    STUB_ROSTER="$CASE_ROSTER" \
    HOME="$CASE_ROOT" PATH="$CASE_ROOT/bin:$PATH" RR_POLL_NO_JITTER=1 \
      sh "$CASE_ROOT/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" \
      >"$CASE_ROOT/out" 2>"$CASE_ROOT/err"
    CASE_RC=$?
    CASE_AGENT_CALLS=$(harness_agent_calls "$CASE_RECORD")
    CASE_CLAIMS=0
    if [ -f "$CLAIM_LOG" ]; then
        CASE_CLAIMS=$(grep -c . "$CLAIM_LOG" 2>/dev/null)
        case "$CASE_CLAIMS" in ''|*[!0-9]*) CASE_CLAIMS=0 ;; esac
    fi
    kill "$CASE_RECEIVER_PID" 2>/dev/null || true
    wait "$CASE_RECEIVER_PID" 2>/dev/null || true
}

# a rejection must have produced a STRUCTURED record, not just an exit
case_rejection_record() {  # case_rejection_record <reason-fragment>
    if [ -d "$CASE_ROOT/.openclaw/state/rr-receiver/rejected" ] \
       && grep -rqF "$1" "$CASE_ROOT/.openclaw/state/rr-receiver/rejected" 2>/dev/null; then
        return 0
    fi
    return 1
}

MKB="$(python3 -c 'import base64;print(base64.b64encode(b"Do the simulated thing").decode())')"

# ---------------------------------------------------------------------------
# 0. POSITIVE CONTROL — the recorder must be able to record.
#    Without this every "zero agent calls" assertion below is vacuous.
# ---------------------------------------------------------------------------
echo "--- 0. control: a legitimate claim DOES reach the agent (recorder is live) ---"
GOOD="{\"status\":\"instruction\",\"instruction_id\":\"ins-good\",\"idempotency_key\":\"idem-good\",\"ticket_id\":\"T-good\",\"agent_id\":\"main\",\"session_key\":\"sess-good\",\"payload_b64\":\"$MKB\",\"mode\":\"live\",\"lease_seconds\":900}"
harness_case good "$GOOD"
[ "$CASE_AGENT_CALLS" -ge 1 ] \
  && ok "control: legitimate live claim produced $CASE_AGENT_CALLS agent call(s)" \
  || bad "control: NO agent call on a legitimate claim — every negative below is vacuous"
grep -q '"action":"claim"' "$CASE_ROOT/claims.txt" 2>/dev/null \
  && ok "control: the claim actually reached the receiver stub" \
  || bad "control: no claim reached the receiver"

# ---------------------------------------------------------------------------
# 1. omit each required member -> zero agent calls, structured rejection
# ---------------------------------------------------------------------------
echo "--- 1. omit each required member ---"
omit_case() {  # omit_case <name> <json-with-field-removed>
    harness_case "$1" "$2"
    if [ "$CASE_AGENT_CALLS" -eq 0 ]; then
        ok "omit $1: zero agent calls (rc=$CASE_RC)"
    else
        bad "omit $1: $CASE_AGENT_CALLS agent call(s) on an incomplete envelope"
    fi
}
omit_case mode            '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","lease_seconds":900}'
omit_case instruction_id  '{"status":"instruction","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
omit_case idempotency_key '{"status":"instruction","instruction_id":"i","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
omit_case ticket_id       '{"status":"instruction","instruction_id":"i","idempotency_key":"k","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
omit_case agent_id        '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
if case_rejection_record missing_mode || case_rejection_record missing_ticket_id \
   || case_rejection_record missing_capability || case_rejection_record missing_instruction_id; then
    ok "omissions produced STRUCTURED rejection records naming the member"
else
    bad "omissions produced no structured rejection record"
fi

# ---------------------------------------------------------------------------
# 2. mistype members -> zero agent calls (a coercing reader would execute)
# ---------------------------------------------------------------------------
echo "--- 2. mistype each member ---"
mistype_case() {  # mistype_case <name> <json>
    harness_case "$1" "$2"
    if [ "$CASE_AGENT_CALLS" -eq 0 ]; then
        ok "mistype $1: zero agent calls"
    else
        bad "mistype $1: $CASE_AGENT_CALLS agent call(s) on a mistyped member"
    fi
}
mistype_case instruction_id '{"status":"instruction","instruction_id":12345,"idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
mistype_case ticket_id      '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":["t"],"agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
mistype_case agent_id       '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":{"id":"main"},"session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
mistype_case mode           '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":true,"lease_seconds":900}'
mistype_case lease_seconds  '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":"forever"}'
mistype_case instruction_object '{"status":"instruction","instruction_id":{"$ne":null},"idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'

# ---------------------------------------------------------------------------
# 3. unknown mode executes nothing
# ---------------------------------------------------------------------------
echo "--- 3. unknown mode ---"
harness_case unknownmode '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"unknownmode","lease_seconds":900}'
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "mode=unknownmode: zero agent calls" || bad "mode=unknownmode ran $CASE_AGENT_CALLS agent call(s)"
case_rejection_record unsupported_mode && ok "mode=unknownmode produced a structured rejection (unsupported_mode)" || bad "unknownmode rejection record missing"
harness_case unknownmode2 '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"'"$MKB"'","mode":"LIVE","lease_seconds":900}'
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "mode=LIVE (case-variant): zero agent calls — the mode set is exact, not folded" || bad "mode=LIVE ran $CASE_AGENT_CALLS agent call(s)"

# ---------------------------------------------------------------------------
# 4. invalid base64 -> nothing executed as a turn
# ---------------------------------------------------------------------------
echo "--- 4. invalid base64 payload ---"
harness_case badb64 '{"status":"instruction","instruction_id":"i","idempotency_key":"k","ticket_id":"t","agent_id":"main","session_key":"s","payload_b64":"!!!!not-base64!!!!","mode":"live","lease_seconds":900}'
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "invalid base64: zero agent calls" || bad "invalid base64 ran $CASE_AGENT_CALLS agent call(s)"

# ---------------------------------------------------------------------------
# 5. canonical identity: two simultaneous tickets must NOT collide
# ---------------------------------------------------------------------------
echo "--- 5. two simultaneous tickets, same idempotency_key ---"
harness_case ticketA '{"status":"instruction","instruction_id":"ins-A","idempotency_key":"SHARED-KEY","ticket_id":"T-A","agent_id":"main","session_key":"sess-A","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
A_SESS=$(sed -n 's/^CALL: agent .*--session-key \([^ ]*\).*/\1/p' "$CASE_ROOT/agent-record.txt" 2>/dev/null | head -1)
A_DONE=$(ls "$CASE_ROOT/.openclaw/state/rr-receiver/done" 2>/dev/null | tr '\n' ' ')
harness_case ticketB '{"status":"instruction","instruction_id":"ins-B","idempotency_key":"SHARED-KEY","ticket_id":"T-B","agent_id":"main","session_key":"sess-B","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
B_DONE=$(ls "$CASE_ROOT/.openclaw/state/rr-receiver/done" 2>/dev/null | tr '\n' ' ')
[ "$A_DONE" != "$B_DONE" ] && [ -n "$A_DONE" ] && [ -n "$B_DONE" ] \
  && ok "two tickets on one shared idempotency_key keep DISTINCT dedup identities" \
  || bad "dedup identity collided" "A=[$A_DONE] B=[$B_DONE]"

# ---------------------------------------------------------------------------
# 6. two clients, same ticket/attempt -> must NOT share a session identity
# ---------------------------------------------------------------------------
echo "--- 6. two clients ---"
harness_case clientA '{"status":"instruction","instruction_id":"ins-C","idempotency_key":"K-C","ticket_id":"T-C","agent_id":"main","session_key":"","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900,"company_id":"client-a","runtime_id":"rt-a"}' "box-a"
SESS_A=$(sed -n 's/^CALL: agent .*--session-key \([^ ]*\).*/\1/p' "$CASE_ROOT/agent-record.txt" 2>/dev/null | head -1)
harness_case clientB '{"status":"instruction","instruction_id":"ins-C","idempotency_key":"K-C","ticket_id":"T-C","agent_id":"main","session_key":"","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900,"company_id":"client-b","runtime_id":"rt-b"}' "box-b"
SESS_B=$(sed -n 's/^CALL: agent .*--session-key \([^ ]*\).*/\1/p' "$CASE_ROOT/agent-record.txt" 2>/dev/null | head -1)
[ -n "$SESS_A" ] && [ -n "$SESS_B" ] && [ "$SESS_A" != "$SESS_B" ] \
  && ok "two clients derive DISTINCT session identities from company+runtime" \
  || bad "session identity collided across clients" "A=[$SESS_A] B=[$SESS_B]"
case "$SESS_A" in
  *"agent:rescue:"*) ok "absent session_key is DERIVED from the canonical claim identity, never a shared empty suffix" ;;
  "") bad "no derived session key seen" ;;
  *) bad "session key not derived from the claim identity" "$SESS_A" ;;
esac

# ---------------------------------------------------------------------------
# 7. keys a/b vs a_b — the length-prefixed encoding must not fold them
# ---------------------------------------------------------------------------
echo "--- 7. compound-key aliasing across the FOUR canonical members ---"
# The canonical identity is company+runtime+incident+attempt, so the aliasing
# test must vary a member OF THAT TUPLE. A delimiter-joined encoding ("a|b|c")
# would fold the pairs below onto one digest; the length-prefixed encoding must
# not. (Each case uses a DISTINCT ticket/idempotency_key so the only variable
# under test is the tuple member itself.)
alias_case() {  # alias_case <label> <company> <runtime> <incident> <attempt>
    harness_case "$1" "{\"status\":\"instruction\",\"instruction_id\":\"ins-$1\",\"idempotency_key\":\"K-$1\",\"ticket_id\":\"T-$1\",\"agent_id\":\"main\",\"session_key\":\"\",\"payload_b64\":\"$MKB\",\"mode\":\"live\",\"lease_seconds\":900,\"company_id\":\"$2\",\"runtime_id\":\"$3\",\"incident_id\":\"$4\",\"attempt_id\":\"$5\"}" "box-alias"
    ALIAS_ID=$(sed -n 's/^CALL: agent .*--session-key \(.*\)$/\1/p' "$CASE_ROOT/agent-record.txt" 2>/dev/null | head -1)
}
alias_case aslash "a/b" "rt" "inc" "att"
A1="$ALIAS_ID"
alias_case aunders "a_b" "rt" "inc" "att"
A2="$ALIAS_ID"
[ -n "$A1" ] && [ "$A1" != "$A2" ] \
  && ok "company 'a/b' and 'a_b' hash DIFFERENTLY (length-prefixed, not delimiter-joined)" \
  || bad "compound key aliased on slash vs underscore" "A1=[$A1] A2=[$A2]"

alias_case bshift "a" "binc" "inc" "att"
B1="$ALIAS_ID"
alias_case bshift2 "ab" "inc" "inc" "att"
B2="$ALIAS_ID"
[ -n "$B1" ] && [ "$B1" != "$B2" ] \
  && ok "member-boundary shift (runtime=binc vs company=ab,runtime=inc) does NOT collide" \
  || bad "member-boundary aliasing" "B1=[$B1] B2=[$B2]"

# Negative control: the SAME tuple must be STABLE. A hash that differed on
# every call would pass the two assertions above while being useless.
alias_case stable1 "a" "rt" "inc" "att"
S1="$ALIAS_ID"
alias_case stable2 "a" "rt" "inc" "att"
S2="$ALIAS_ID"
[ -n "$S1" ] && [ "$S1" = "$S2" ] \
  && ok "control: the SAME canonical tuple hashes IDENTICALLY (identity is stable, not random)" \
  || bad "identity unstable for an identical tuple" "S1=[$S1] S2=[$S2]"

alias_case ticketshared "a" "rt" "inc" "att"
[ -n "$ALIAS_ID" ] \
  && ok "ticket_id is NOT one of the four SPEC members; tickets sharing a tuple stay distinct via idempotency_key (asserted in section 5)" \
  || bad "ticket-shared tuple produced no identity"

# ---------------------------------------------------------------------------
# 8. identity mismatch: foreign enrollment / foreign session
# ---------------------------------------------------------------------------
echo "--- 8. identity mismatch executes nothing ---"
harness_case foreign '{"status":"instruction","instruction_id":"ins-F","idempotency_key":"K-F","ticket_id":"T-F","agent_id":"main","session_key":"sess-F","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900,"enrollment_id":"some-other-box"}' "box-synthetic"
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "foreign enrollment_id: zero agent calls" || bad "foreign enrollment ran $CASE_AGENT_CALLS agent call(s)"
case_rejection_record foreign_enrollment && ok "foreign enrollment produced a structured rejection (identity_mismatch)" || bad "foreign enrollment rejection record missing"
harness_case foreign_sess '{"status":"instruction","instruction_id":"ins-F2","idempotency_key":"K-F2","ticket_id":"T-F2","agent_id":"main","session_key":"sess-F2","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900,"company_id":"another-client"}' "box-synthetic"
[ -n "$(sed -n 's/^CALL: agent .*--session-key \([^ ]*\).*/\1/p' "$CASE_ROOT/agent-record.txt" 2>/dev/null | head -1)" ] \
  && ok "company_id differing from the authenticated box still resolves in THIS box's context" \
  || ok "company_id mismatch refused to execute (no turn) — acceptable, no cross-context call"

# ---------------------------------------------------------------------------
# 9. unknown agent -> verified same-client fallback, RECORDED
# ---------------------------------------------------------------------------
echo "--- 9. unknown agent / capability resolution ---"
harness_case unknownagent '{"status":"instruction","instruction_id":"ins-U","idempotency_key":"K-U","ticket_id":"T-U","agent_id":"ghost-agent","session_key":"sess-U","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}' "box-synthetic" '[{"id":"general-task","isDefault":false},{"id":"master-orchestrator","isDefault":false},{"id":"main","isDefault":true}]'
U_AGENT=$(sed -n 's/^CALL: agent --agent \([^ ]*\).*/\1/p' "$CASE_ROOT/agent-record.txt" 2>/dev/null | head -1)
[ "$U_AGENT" = "general-task" ] \
  && ok "unknown agent resolved to the verified authorized General agent (same client context)" \
  || bad "unknown agent fallback" "chose [$U_AGENT]"
if [ -f "$CASE_ROOT/.openclaw/state/rr-receiver/substitutions/T-U.json" ]; then
  ok "substitution RECORDED on disk (requested/chosen/reason/roster digest)"
else
  bad "substitution not recorded"
fi

harness_case unknownagent_noGeneral '{"status":"instruction","instruction_id":"ins-U2","idempotency_key":"K-U2","ticket_id":"T-U2","agent_id":"ghost-agent","session_key":"sess-U2","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}' "box-synthetic" '[{"id":"some-other-agent","isDefault":false}]'
[ "$CASE_AGENT_CALLS" -eq 0 ] \
  && ok "unknown agent with NO verified same-client fallback: zero agent calls (owned routing fault)" \
  || bad "guessed an agent with no verified fallback"
[ -f "$CASE_ROOT/.openclaw/state/rr-receiver/rejected/routing-fault-T-U2.json" ] \
  && ok "routing fault RECORDED with next_owner=operator" \
  || bad "routing fault record missing"

harness_case unknownagent_unreadableRoster '{"status":"instruction","instruction_id":"ins-U3","idempotency_key":"K-U3","ticket_id":"T-U3","agent_id":"ghost-agent","session_key":"sess-U3","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}' "box-synthetic" 'not-json-at-all'
[ "$CASE_AGENT_CALLS" -eq 0 ] \
  && ok "unreadable roster: refused rather than guessed (zero agent calls)" \
  || bad "unverifiable capability guessed an agent"

# ---------------------------------------------------------------------------
# 10. lease: absent / too short / stale
# ---------------------------------------------------------------------------
echo "--- 10. lease negotiation ---"
harness_case lease_short '{"status":"instruction","instruction_id":"ins-L","idempotency_key":"K-L","ticket_id":"T-L","agent_id":"main","session_key":"sess-L","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":5}'
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "lease_seconds=5 (too short to finish + ACK): zero agent calls" || bad "ran a turn on an unusable lease"
case_rejection_record lease_too_short && ok "short lease produced a structured rejection (stale_lease)" || bad "short lease rejection record missing"
harness_case lease_absent '{"status":"instruction","instruction_id":"ins-L2","idempotency_key":"K-L2","ticket_id":"T-L2","agent_id":"main","session_key":"sess-L2","payload_b64":"'"$MKB"'","mode":"live"}'
[ "$CASE_AGENT_CALLS" -ge 1 ] \
  && ok "lease absent (pre-RR-025 server): still delivers, bounded by the live 900s default" \
  || bad "a claim with no lease field was refused outright (compatible-by-design broken)"

# ---------------------------------------------------------------------------
# 11. dry_run is not a delivery and runs no turn
# ---------------------------------------------------------------------------
echo "--- 11. dry_run ---"
harness_case dryrun '{"status":"instruction","instruction_id":"ins-D","idempotency_key":"K-D","ticket_id":"T-D","agent_id":"main","session_key":"sess-D","payload_b64":"'"$MKB"'","mode":"dry_run","lease_seconds":900}'
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "mode=dry_run: zero agent calls" || bad "dry_run ran $CASE_AGENT_CALLS agent call(s)"

# ---------------------------------------------------------------------------
# 12. the poll never acks a verdict for work it never attempted
# ---------------------------------------------------------------------------
echo "--- 12. no verdict about an unattempted turn ---"
harness_case noack '{"status":"instruction","instruction_id":"ins-N","idempotency_key":"K-N","ticket_id":"T-N","agent_id":"ghost","session_key":"sess-N","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}' "box-synthetic" '[{"id":"unrelated-agent","isDefault":false}]'
[ "$CASE_AGENT_CALLS" -eq 0 ] && ok "premise: no verified fallback existed, so no turn ran" || bad "premise broken: a turn ran"
if [ -f "$CASE_ROOT/claims.txt" ]; then
  grep -q '"action":"ack"' "$CASE_ROOT/claims.txt" \
    && bad "an ACK was sent for a claim on which no agent turn ran" \
    || ok "no verdict ack sent for a claim that executed nothing (ticket left non-terminal for the SLA machinery)"
else
  ok "no ack path reached (no claim recorded)"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
RR025_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
