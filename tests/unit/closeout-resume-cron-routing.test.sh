#!/usr/bin/env bash
# tests/unit/closeout-resume-cron-routing.test.sh
#
# CI guard for the CLOSEOUT BELT's client-leak and dead-safety-control defects.
#
# WHY THIS MATTERS MORE THAN IT LOOKS. 37-zhc-closeout/scripts/resume-closeout-cron.sh
# gates on `buildCompletedAt` ALONE. Once that field is written it launches
# run-closeout.sh in-process (the full multi-message client celebration) and dispatches
# a `[CLOSEOUT-RESUME]` self-ping. That self-ping used to resolve `.ownerChat` FIRST --
# so the message, whose own text said the owner is not a recipient, was addressed to
# the owner.
#
# `buildCompletedAt` is precisely the field the rest of this incident's fixes exist to
# unblock. The moment a legitimate build can finally write it, every affected box would
# have fired internal build jargon into the client's DM alongside a celebration many of
# them had already received for an earlier, incomplete build. That is why the routing
# fix has to reach boxes BEFORE anything that enables the write.
#
# GROUPS (each functional assertion is paired with a mutation proof):
#   (1) NEVER_TO_OWNER   -- the self-ping is never addressed to .ownerChat, even when
#                           ownerChat is set and no operator chat is configured.
#   (2) FAIL_SAFE        -- with no operator chat the send is SKIPPED, not redirected,
#                           and run-closeout.sh still fires (it is the primary path).
#   (3) MSG_CONSISTENT   -- the message no longer both says "do not message the owner"
#                           and get addressed to the owner.
#   (4) PAUSE_IS_REAL    -- .closeoutResumePaused actually gates the heavy work. It was
#                           a safety control that did nothing: production code only ever
#                           WROTE it, no belt READ it, and operators were told to rely
#                           on it.
#
# HERMETIC: runs a copy of the belt from inside a private sandbox with OC_ROOT/HOME
# pointed there and a fake `openclaw` on PATH. run-closeout.sh is STUBBED, so the real
# closeout never runs and no client message is ever produced.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BELT="$REPO_ROOT/37-zhc-closeout/scripts/resume-closeout-cron.sh"
FAKE_OC="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== closeout-resume-cron-routing.test.sh ==="
echo ""

for _need in "$BELT" "$FAKE_OC"; do
  [[ -f "$_need" ]] || { echo "FAIL: required file missing: $_need"; exit 1; }
done
bash -n "$BELT" && pass "0a: resume-closeout-cron.sh is bash -n clean" \
                 || fail "0a: resume-closeout-cron.sh has a syntax error"

if [[ -d /data/.openclaw ]]; then
  echo "!! SKIPPED: /data/.openclaw exists on this host — cannot guarantee fixture isolation"
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit $(( FAIL > 0 ))
fi

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

OWNER_CHAT="111222333"
OPERATOR_CHAT="555000111"

# $1 = box name, $2 = state JSON
_mkbox() {
  local name="$1" state_json="$2"
  local h="$SANDBOX/$name"
  local skill="$h/.openclaw/skills/37-zhc-closeout/scripts"
  mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"
  cp "$BELT" "$skill/resume-closeout-cron.sh"
  cp "$REPO_ROOT/37-zhc-closeout/scripts/lib-closeout-state.sh" "$skill/"
  local shared="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  mkdir -p "$shared"
  cp "$REPO_ROOT/23-ai-workforce-blueprint/scripts/"{lib-workforce-state.sh,workforce_state.py,workforce_completion.py,interview_eligibility.py} "$shared/"
  # STUB run-closeout.sh: records that it fired; never runs the real closeout.
  cat > "$skill/run-closeout.sh" <<STUBEOF
#!/usr/bin/env bash
echo "STUB-RUN-CLOSEOUT-FIRED" >> "$h/closeout-fired.log"
STUBEOF
  chmod +x "$skill/run-closeout.sh"
  cat > "$h/bin/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FAKE_OC" "\$@"
SHIM
  chmod +x "$h/bin/openclaw"
  printf '%s' "$state_json" > "$h/.openclaw/workspace/.workforce-build-state.json"
  printf '[]' > "$h/jobs.json"
  : > "$h/calls.log"
  : > "$h/closeout-fired.log"
  printf '%s' "$h"
}

# The belt launches run-closeout.sh with `nohup ... &`, so its marker write is ASYNC
# and races the assertion below. Poll for it in the foreground with a bounded timeout
# rather than assuming it has landed (this was a real CI-only flake: it passed on macOS
# and failed on the Linux runner).
#   $1 = marker file, $2 = timeout in seconds. Returns 0 if it appeared.
_wait_for_marker() {
  local f="$1" limit="${2:-15}" waited=0
  while (( waited < limit )); do
    [[ -s "$f" ]] && return 0
    sleep 1
    waited=$(( waited + 1 ))
  done
  [[ -s "$f" ]]
}

# $1 = box home; remaining args = extra env (e.g. the operator chat)
_run() {
  local h="$1"; shift
  env -i \
    PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$h" \
    TMPDIR="${TMPDIR:-/tmp}" \
    OC_ROOT="$h/.openclaw" \
    FAKE_OC_JOBS_FILE="$h/jobs.json" \
    FAKE_OC_CALLS_FILE="$h/calls.log" \
    "$@" \
    bash "$h/.openclaw/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh" \
    >"$h/run.out" 2>&1
  return 0
}

# buildCompletedAt SET + a non-terminal closeout: the exact shape that is not gated.
STATE_OPEN='{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "companyName": "Fixture Co",
  "agentName": "FixtureOrchestrator",
  "ownerChat": "'"$OWNER_CHAT"'",
  "buildCompletedAt": "2026-01-01T00:00:00Z",
  "closeoutStatus": "pending",
  "departments": [{"id": "alpha", "status": "done"}]
}'

# ---------------------------------------------------------------------------
# (1)+(2) NEVER_TO_OWNER + FAIL_SAFE
# ---------------------------------------------------------------------------
echo ""
echo "--- (1) NEVER_TO_OWNER: ownerChat set, NO operator chat configured ---"
B1="$(_mkbox box1 "$STATE_OPEN")"
_run "$B1"
if grep -E "(--target|[[:space:]]-t)[[:space:]]*$OWNER_CHAT" "$B1/calls.log" >/dev/null 2>&1; then
  fail "1a: the [CLOSEOUT-RESUME] self-ping was addressed to the CLIENT's chat"
else
  pass "1a: no message was addressed to the client's chat"
fi
if _wait_for_marker "$B1/closeout-fired.log" 15; then
  pass "2a: run-closeout.sh still fired in-process (the primary path is unaffected)"
else
  fail "2a: skipping the self-ping also skipped run-closeout.sh — the closeout was lost"
fi
if grep -q "SKIPPING the internal self-ping rather than sending it to the client" "$B1/run.out" 2>/dev/null; then
  pass "2b: the skip is logged loudly, with the remedy"
else
  fail "2b: the belt went quiet without explaining why nothing was sent"
fi

echo ""
echo "--- (1b) with an operator chat configured the self-ping DOES go out (to the operator) ---"
B1B="$(_mkbox box1b "$STATE_OPEN")"
_run "$B1B" OPERATOR_ESCALATION_CHAT_ID="$OPERATOR_CHAT"
if grep -E "(--target|[[:space:]]-t)[[:space:]]*$OPERATOR_CHAT" "$B1B/calls.log" >/dev/null 2>&1; then
  pass "1b: the self-ping was delivered to the operator chat"
else
  fail "1b: no self-ping reached the operator chat ($(tail -2 "$B1B/run.out" | tr '\n' ' '))"
fi
if grep -E "(--target|[[:space:]]-t)[[:space:]]*$OWNER_CHAT" "$B1B/calls.log" >/dev/null 2>&1; then
  fail "1c: the client's chat ALSO received the internal message"
else
  pass "1c: the client's chat received nothing"
fi

# ---------------------------------------------------------------------------
# (3) MSG_CONSISTENT
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) MSG_CONSISTENT: a message claiming the owner is not a recipient must not be sent to the owner ---"
if grep -q 'Do NOT message the owner' "$BELT"; then
  # If that phrasing survives, it must be provably unreachable by the owner. Since we
  # already assert ownerChat is never a target, the self-contradiction is what we flag.
  fail "3a: the self-contradicting 'Do NOT message the owner' phrasing is still in the message body"
else
  pass "3a: the self-contradicting phrasing is gone"
fi
if grep -q 'INTERNAL operator/agent traffic' "$BELT"; then
  pass "3b: the message states plainly that it is internal traffic"
else
  fail "3b: the message does not identify itself as internal traffic"
fi

echo ""
echo "--- (1-MUT) MUTATION PROOF: the old ownerChat-first routing reaches the client ---"
B1M="$(_mkbox box1m "$STATE_OPEN")"
MUT1="$B1M/.openclaw/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh"
python3 - "$MUT1" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = 'target_chat="$operator_chat"\n'
new = ('owner_chat=$(state_get \'.ownerChat\')\n'
       'if [[ -z "$owner_chat" || "$owner_chat" == "null" ]]; then\n'
       '  target_chat="$operator_chat"\n'
       'else\n'
       '  target_chat="$owner_chat"\n'
       'fi\n')
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, new, 1))
PYEOF
mut1_rc=$?
if (( mut1_rc != 0 )); then
  fail "1-MUT: could not reinstate ownerChat-first routing — cannot prove 1a discriminates"
else
  _run "$B1M"
  if grep -E "(--target|[[:space:]]-t)[[:space:]]*$OWNER_CHAT" "$B1M/calls.log" >/dev/null 2>&1; then
    pass "1-MUT: the old routing DOES deliver internal build jargon to the client — 1a is a real, non-vacuous check"
  else
    fail "1-MUT: the reinstated routing sent nothing to the client — 1a proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
# (4) PAUSE_IS_REAL
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) PAUSE_IS_REAL: .closeoutResumePaused must actually stop the heavy work ---"
STATE_PAUSED="${STATE_OPEN/\"closeoutStatus\": \"pending\"/\"closeoutStatus\": \"pending\", \"closeoutResumePaused\": true, \"closeoutResumePausedReason\": \"operator hold\"}"
B4="$(_mkbox box4 "$STATE_PAUSED")"
_run "$B4" OPERATOR_ESCALATION_CHAT_ID="$OPERATOR_CHAT"
sleep 3   # settle window: if a launch were going to happen, it would land by now
if [[ -s "$B4/closeout-fired.log" ]]; then
  fail "4a: run-closeout.sh fired on a PAUSED box — the client-facing closeout ran anyway"
else
  pass "4a: run-closeout.sh did NOT fire while paused"
fi
if grep -qE "^message send" "$B4/calls.log" 2>/dev/null; then
  fail "4b: a self-ping was dispatched on a PAUSED box"
else
  pass "4b: no self-ping dispatched while paused"
fi
if grep -q "PAUSED: .closeoutResumePaused=true" "$B4/run.out" 2>/dev/null; then
  pass "4c: the pause is logged with its reason and how it clears"
else
  fail "4c: the pause was not logged"
fi

echo ""
echo "--- (4-MUT) MUTATION PROOF: without the gate, a PAUSED box still fires the closeout ---"
B4M="$(_mkbox box4m "$STATE_PAUSED")"
MUT4="$B4M/.openclaw/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh"
python3 - "$MUT4" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
start = src.index('# ---- OPERATOR PAUSE GATE')
end = src.index('# ---- work to do: dispatch CLOSEOUT-RESUME self-ping ----', start)
open(path, "w").write(src[:start] + src[end:])
PYEOF
mut4_rc=$?
if (( mut4_rc != 0 )); then
  fail "4-MUT: could not remove the pause gate — cannot prove 4a discriminates"
else
  _run "$B4M" OPERATOR_ESCALATION_CHAT_ID="$OPERATOR_CHAT"
  if _wait_for_marker "$B4M/closeout-fired.log" 15; then
    pass "4-MUT: without the gate a PAUSED box DOES fire run-closeout.sh — 4a is a real, non-vacuous check (the field really did gate nothing)"
  else
    fail "4-MUT: the ungated box did not fire either — 4a proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all closeout-resume-cron-routing checks pass"
exit 0
