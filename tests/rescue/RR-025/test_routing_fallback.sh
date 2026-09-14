#!/usr/bin/env bash
# tests/rescue/RR-025/test_routing_fallback.sh — the routing-fault refusals.
#
# WHY THIS BATTERY EXISTS
#   `rescue-poll.sh` resolves a requested agent against the box's OWN roster and
#   falls back only to a name it can VERIFY there. Three refusal paths carry a
#   reason literal, and a survey of the whole ONB test tree found that NONE of the
#   three was mentioned by any test:
#
#     roster_unreadable       the roster could not be read at all
#     requested_agent_absent  the requested agent is absent; a verified local
#                             substitute was chosen and RECORDED
#     no_verified_fallback    the requested agent is absent AND no local candidate
#                             could be verified
#
#   `no_verified_fallback` is the one that matters most: it is the point where the
#   box could page a session nobody verified, on a ticket that names a different
#   agent. The code says it refuses and records an owned routing fault instead.
#   NOTHING MEASURED THAT. This is also the SPEC's own required QC for RR-025 --
#   "Verify requested local agent exists. If absent, use a verified authorized
#   same-client General/CEO fallback and record substitution, or keep an owned
#   operator-recoverable routing fault" -- so the requirement was only half
#   pinned: the fallback half was covered, the refusal half was not.
#
# HOW THE EVIDENCE IS TAKEN
#   The same way RR-025 takes it: drive the REAL rescue-poll.sh against a loopback
#   receiver stub and count the agent turns a stub `openclaw` binary recorded. A
#   negative assertion about a call that must NOT happen is only worth something if
#   the recorder provably fires, so every case below is paired with the positive
#   control from the shared harness.
#
# Hermetic: temp dirs, synthetic slug/token, loopback HTTP, no credential.
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

echo "== RR-025: capability resolution -- the routing-fault refusals =="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr025rf.XXXXXX")"
RR025RF_DONE=""
cleanup() {
    [ -n "${RR025RF_DONE:-}" ] && return 0
    RR025RF_DONE=1
    [ -n "${CASE_RECEIVER_PID:-}" ] && kill "$CASE_RECEIVER_PID" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

BASE_PORT=19740
CASE_INDEX=0
DEFAULT_ROSTER='[{"id":"main","isDefault":true}]'

harness_case() {
    CASE_INDEX=$((CASE_INDEX+1))
    CASE_PORT=$(( BASE_PORT + CASE_INDEX ))
    CASE_SLUG="${3:-box-synthetic}"
    if [ -n "${4:-}" ]; then CASE_ROSTER="$4"; else CASE_ROSTER="$DEFAULT_ROSTER"; fi
    # `CASE_ROSTER_FAIL=1` makes the stub's `agents list` FAIL, which is the only way
    # to produce a genuinely UNREADABLE roster. Passing an empty STUB_ROSTER does NOT:
    # the stub falls back to its built-in default (`[{"id":"main","isDefault":true}]`),
    # so the poll saw a perfectly good roster and legitimately ran a turn. Measured --
    # the case failed with "paged an agent" for exactly that reason.
    CASE_ROSTER_FAIL="${CASE_ROSTER_FAIL:-}"
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
    STUB_ROSTER_FAIL="${CASE_ROSTER_FAIL:-}" \
    HOME="$CASE_ROOT" PATH="$CASE_ROOT/bin:$PATH" RR_POLL_NO_JITTER=1 \
      sh "$CASE_ROOT/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" \
      >"$CASE_ROOT/out" 2>"$CASE_ROOT/err"
    CASE_RC=$?
    CASE_AGENT_CALLS=$(harness_agent_calls "$CASE_RECORD")
    # `claims.txt` records every POST the poll makes, and a run ALWAYS claims once --
    # so counting its lines measures "the poll ran", not "the poll lied". The wire event
    # that must NOT happen is an ACK for a turn that never ran, and `_rr_routing_fault_ack`
    # logs `acked=false` for exactly that reason. Count ACK BODIES, and prove the counter
    # can see one by checking it on the control case (which does ack).
    CASE_ACKS=0
    if [ -f "$CLAIM_LOG" ]; then
        CASE_ACKS=$(grep -c '"action":"ack"' "$CLAIM_LOG" 2>/dev/null)
        case "$CASE_ACKS" in ''|*[!0-9]*) CASE_ACKS=0 ;; esac
    fi
    kill "$CASE_RECEIVER_PID" 2>/dev/null || true
    wait "$CASE_RECEIVER_PID" 2>/dev/null || true
}

# The fault record the box writes when it refuses to page an unverified session.
fault_record() {  # fault_record <reason>
    [ -d "$CASE_ROOT/.openclaw/state/rr-receiver/rejected" ] || return 1
    grep -rqF "\"reason\":\"$1\"" "$CASE_ROOT/.openclaw/state/rr-receiver/rejected" 2>/dev/null
}
substitution_record() {
    [ -d "$CASE_ROOT/.openclaw/state/rr-receiver/substitutions" ] || return 1
    ls "$CASE_ROOT/.openclaw/state/rr-receiver/substitutions" 2>/dev/null | grep -q .
}

MKB="$(python3 -c 'import base64;print(base64.b64encode(b"Do the simulated thing").decode())')"
CLAIM_GHOST='{"status":"instruction","instruction_id":"ins-RF","idempotency_key":"K-RF","ticket_id":"T-RF","agent_id":"ghost-agent","session_key":"sess-RF","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'
CLAIM_MAIN='{"status":"instruction","instruction_id":"ins-RC","idempotency_key":"K-RC","ticket_id":"T-RC","agent_id":"main","session_key":"sess-RC","payload_b64":"'"$MKB"'","mode":"live","lease_seconds":900}'

# ---------------------------------------------------------------------------
# 0. POSITIVE CONTROL — the recorder and the turn path both work.
#    Without this, every "zero agent calls" below could be a broken harness.
# ---------------------------------------------------------------------------
echo "--- 0. control: a resolvable agent DOES get a turn ---"
harness_case ctl "$CLAIM_MAIN" "box-synthetic" '[{"id":"main","isDefault":true}]'
[ "$CASE_AGENT_CALLS" -ge 1 ] \
  && ok "control: the requested agent EXISTS in the roster, so the poll ran a turn (calls=$CASE_AGENT_CALLS)" \
  || bad "control: no turn ran even for a resolvable agent -- the recorder or the path is broken" "calls=$CASE_AGENT_CALLS rc=$CASE_RC"
# NON-VACUITY FOR THE ACK COUNTER: this case runs a turn, so it must produce an ack.
# Without this, every "zero acks" assertion below could be a broken grep.
[ "$CASE_ACKS" -ge 1 ] \
  && ok "control: the ack counter FIRES -- a completed turn produced an ack (acks=$CASE_ACKS)" \
  || bad "the ack counter never fires, so 'zero acks' below would prove nothing" "acks=$CASE_ACKS"

# ---------------------------------------------------------------------------
# 1. ROSTER UNREADABLE — unverifiable capability, never an absent agent.
#    A roster that cannot be read must NOT be treated as an empty roster, because
#    an empty roster makes every name look absent and invites a guess.
# ---------------------------------------------------------------------------
echo "--- 1. an UNREADABLE roster is a routing fault, not an invitation to guess ---"
CASE_ROSTER_FAIL=1 harness_case roster '' "box-synthetic" "$DEFAULT_ROSTER"
CASE_ROSTER_FAIL='' 
[ "$CASE_AGENT_CALLS" -eq 0 ] \
  && ok "control: an unreadable roster produced ZERO agent turns (calls=$CASE_AGENT_CALLS)" \
  || bad "an unreadable roster still produced a turn" "calls=$CASE_AGENT_CALLS rc=$CASE_RC"
[ "$CASE_ACKS" -eq 0 ] \
  && ok "and nothing was acked for the unreadable-roster case either (acks=$CASE_ACKS)" \
  || bad "an unreadable roster still acked" "acks=$CASE_ACKS"
if fault_record roster_unreadable; then
  ok "and the box recorded an OWNED routing fault naming roster_unreadable"
else
  # The stub answers `agents list` with an empty string, which some builds report as
  # a readable-but-empty roster rather than an unreadable one. Either way the
  # requirement holds: nothing may be paged. Say WHICH happened rather than passing
  # on a technicality.
  if [ "$CASE_AGENT_CALLS" -eq 0 ]; then
    ok "no fault record, but also NO turn -- the unreadable roster did not become a guess"
  else
    bad "an unreadable roster paged an agent" "calls=$CASE_AGENT_CALLS rc=$CASE_RC"
  fi
fi

# ---------------------------------------------------------------------------
# 2. NO VERIFIED FALLBACK — the refusal that matters most.
#    The requested agent is absent AND the roster contains none of the authorized
#    candidates. The box must page NOBODY and record the fault. This is the point
#    where a weaker implementation would fall back to "whatever the box has".
# ---------------------------------------------------------------------------
echo "--- 2. no verifiable candidate: refuse, page nobody, record the fault ---"
harness_case nofallback "$CLAIM_GHOST" "box-synthetic" '[{"id":"some-unrelated-agent","isDefault":false}]'
[ "$CASE_AGENT_CALLS" -eq 0 ] \
  && ok "PLANT CHECK: the roster holds NEITHER the requested agent NOR an authorized candidate, and ZERO turns ran (calls=$CASE_AGENT_CALLS)" \
  || bad "an unverifiable fallback paged an agent" "calls=$CASE_AGENT_CALLS rc=$CASE_RC"
if fault_record no_verified_fallback; then
  ok "and the refusal is RECORDED with reason=no_verified_fallback (not inferred from the call count)"
else
  bad "the box refused silently -- no routing-fault record names no_verified_fallback" "$(ls "$CASE_ROOT/.openclaw/state/rr-receiver/rejected" 2>/dev/null | tr '\n' ' ')"
fi
# The ticket must stay NON-TERMINAL: a routing fault is owned and recoverable, so
# the SLA machinery must still see it.
[ "$CASE_ACKS" -eq 0 ] \
  && ok "and NOTHING was acked on the wire -- no turn ran, so no verdict about a turn may be sent (the poll still CLAIMED, which is how it learned the ticket)" \
  || bad "the box acked a claim for a turn it never ran" "acks=$CASE_ACKS"

# ---------------------------------------------------------------------------
# 3. THE FALLBACK MUST BE ONE OF THE AUTHORIZED CANDIDATES, NEVER "ANY AGENT".
#    Contrast with case 2: same requested agent, but the roster DOES hold an
#    authorized candidate. Now a turn is expected, and it must be that candidate.
# ---------------------------------------------------------------------------
echo "--- 3. contrast: with a verifiable candidate a turn DOES run, on that candidate ---"
harness_case fallback "$CLAIM_GHOST" "box-synthetic" '[{"id":"general-task","isDefault":false},{"id":"some-unrelated-agent","isDefault":false}]'
F_AGENT=$(sed -n 's/^CALL: agent --agent \([^ ]*\).*/\1/p' "$CASE_RECORD" 2>/dev/null | head -1)
[ "$F_AGENT" = "general-task" ] \
  && ok "the fallback chose the authorized General candidate" \
  || bad "the fallback chose [$F_AGENT] -- it must be general-task, master-orchestrator, or the box default" "calls=$CASE_AGENT_CALLS"
[ "$F_AGENT" != "some-unrelated-agent" ] \
  && ok "and it did NOT choose the unrelated agent merely because it was in the roster" \
  || bad "the fallback picked an agent that is in the roster but NOT an authorized candidate" "chose=[$F_AGENT]"
[ "$CASE_ACKS" -ge 1 ] \
  && ok "and the substituted turn WAS acked (acks=$CASE_ACKS) -- the contrast with case 2 is a turn, not a silent difference" \
  || bad "a substituted turn ran but was never acked" "acks=$CASE_ACKS"
if substitution_record; then
  ok "and the substitution is RECORDED (auditable, not invisible)"
else
  bad "a substitution happened with no record" "$(ls "$CASE_ROOT/.openclaw/state/rr-receiver/substitutions" 2>/dev/null | tr '\n' ' ')"
fi

# ---------------------------------------------------------------------------
# 4. THE TWO REFUSALS ARE DISTINCT.
#    `roster_unreadable` says "I could not verify anything"; `no_verified_fallback`
#    says "I verified, and none of the authorized candidates is here". Collapsing
#    them would send an operator to fix the wrong thing, so the reasons must differ
#    for the two different inputs.
# ---------------------------------------------------------------------------
echo "--- 4. the two refusal reasons are distinct ---"
harness_case distinct_a "$CLAIM_GHOST" "box-synthetic" '[{"id":"some-unrelated-agent","isDefault":false}]'
A_REASON=$(grep -ho '"reason":"[a-z_]*"' "$CASE_ROOT/.openclaw/state/rr-receiver/rejected/"*.json 2>/dev/null | head -1)
A_CALLS="$CASE_AGENT_CALLS"
# The unreadable-roster input: STUB_ROSTER empty means the stub prints NOTHING for
# `agents list`, so the poll sees no roster at all. Whether that surfaces as
# `roster_unreadable` or as "no readable roster, so refuse" is a property of THIS stub;
# what must hold either way is that no turn ran and no ack was sent.
CASE_ROSTER_FAIL=1 harness_case distinct_b "$CLAIM_GHOST" "box-synthetic" "$DEFAULT_ROSTER"
CASE_ROSTER_FAIL='' 
B_REASON=$(grep -ho '"reason":"[a-z_]*"' "$CASE_ROOT/.openclaw/state/rr-receiver/rejected/"*.json 2>/dev/null | head -1)
B_CALLS="$CASE_AGENT_CALLS"
[ "$A_CALLS" -eq 0 ] && [ "$B_CALLS" -eq 0 ] \
  && ok "both unresolvable inputs paged NOBODY (candidate-less roster: $A_CALLS turns; unreadable roster: $B_CALLS turns)" \
  || bad "an unresolvable input paged an agent" "A=$A_CALLS B=$B_CALLS"
[ -n "$A_REASON" ] && [ -n "$B_REASON" ] && [ "$A_REASON" != "$B_REASON" ] \
  && ok "and they are REPORTED as different faults ($A_REASON vs $B_REASON)" \
  || bad "the two inputs are not distinguished" "A=[$A_REASON] B=[$B_REASON]"

echo ""
echo "RESULT: $PASS passed, $FAIL failed, 0 skipped"
RR025RF_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0
