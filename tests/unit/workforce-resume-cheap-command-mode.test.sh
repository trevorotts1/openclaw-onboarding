#!/usr/bin/env bash
# tests/unit/workforce-resume-cheap-command-mode.test.sh
#
# Acceptance tests for Fix C(ii)+(iii) (REALESTATE-DEPT-GATING-FIX-SPEC-2026-07-11.md,
# Section 3 "FIX C"): the workforce-build-resume cron must not spend a full
# LLM turn every 15 min just to discover "nothing to resume", and a dispatch
# that hits a gateway rate-limit/error must back off rather than retry at the
# same fixed cadence.
#
# C2  workforce-build-resume is registered in COMMAND mode (runs
#     resume-workforce-build.sh directly — zero LLM tokens per tick) by
#     scripts/ensure-pipeline-crons.sh, the shared registrar called by both
#     install.sh and update-skills.sh. With a build-state showing NO
#     resumable work, running resume-workforce-build.sh performs ZERO
#     `openclaw message send` dispatches (no agent-turn trigger at all).
# C3  A dispatch that hits a rate-limit/error signal (429) writes a durable
#     backoff marker and widens the next-allowed dispatch time; an immediate
#     re-fire is correctly skipped (no second dispatch attempt) while the
#     backoff window is open.
#
# MUTATION PROOF (C2): a sandboxed copy of ensure-pipeline-crons.sh with the
# command-mode registration reverted to the historical agent-message form
# (_oc_cron_silent_main, feeding a system-event) registers the SAME cron name
# as an "agentTurn" job instead of "command" — proving C2's kind=="command"
# assertion is a real, non-vacuous check.
#
# Runs hermetically; never touches a real ~/.openclaw or network.
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== workforce-resume-cheap-command-mode.test.sh ==="
echo ""

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

_mkbin() {
  local dir="$1"
  mkdir -p "$dir"
  cat > "$dir/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FIXTURE" "\$@"
SHIM
  chmod +x "$dir/openclaw"
}

# ---------------------------------------------------------------------------
# C2a — ensure-pipeline-crons.sh registers workforce-build-resume in COMMAND mode
# ---------------------------------------------------------------------------
echo "--- C2a: workforce-build-resume registered as COMMAND kind (zero LLM tokens/tick) ---"
H_C2="$SANDBOX/home-c2"; bin_c2="$SANDBOX/bin-c2"; J_C2="$SANDBOX/jobs-c2.json"; C_C2="$SANDBOX/calls-c2.log"
mkdir -p "$H_C2/.openclaw/skills/23-ai-workforce-blueprint/scripts" "$H_C2/.openclaw/workspace"
cp "$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" \
  "$H_C2/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
chmod +x "$H_C2/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mkbin "$bin_c2"; printf '[]' > "$J_C2"; : > "$C_C2"

HOME="$H_C2" PATH="$bin_c2:$PATH" FAKE_OC_JOBS_FILE="$J_C2" FAKE_OC_CALLS_FILE="$C_C2" \
  bash "$REPO_ROOT/scripts/ensure-pipeline-crons.sh" > "$SANDBOX/c2-ensure.log" 2>&1 || true

kind_c2=$(python3 -c "
import json
jobs=json.load(open('$J_C2'))
m=[j.get('kind','') for j in jobs if j.get('name')=='workforce-build-resume']
print(m[0] if m else 'MISSING')
")
[ "$kind_c2" = "command" ] && pass "C2a: workforce-build-resume registered with kind=command (not agentTurn)" \
                            || fail "C2a: workforce-build-resume kind='$kind_c2' (expected 'command')"

cmd_c2=$(python3 -c "
import json
jobs=json.load(open('$J_C2'))
m=[j.get('command','') for j in jobs if j.get('name')=='workforce-build-resume']
print(m[0] if m else '')
")
case "$cmd_c2" in
  *resume-workforce-build.sh*) pass "C2b: the registered command runs resume-workforce-build.sh directly ('$cmd_c2')" ;;
  *) fail "C2b: registered command does not reference resume-workforce-build.sh: '$cmd_c2'" ;;
esac

# ---------------------------------------------------------------------------
# C2c — zero dispatch when there is genuinely nothing to resume
# ---------------------------------------------------------------------------
echo ""
echo "--- C2c: zero agent-turn dispatch when build-state shows no resumable work ---"
H_C2b="$SANDBOX/home-c2b"; bin_c2b="$SANDBOX/bin-c2b"; J_C2b="$SANDBOX/jobs-c2b.json"; C_C2b="$SANDBOX/calls-c2b.log"
mkdir -p "$H_C2b/.openclaw/workspace"; _mkbin "$bin_c2b"
printf '[{"name":"workforce-build-resume","id":"fake-001","kind":"command"}]' > "$J_C2b"
: > "$C_C2b"
cat > "$H_C2b/.openclaw/workspace/.workforce-build-state.json" <<'EOF'
{"interviewComplete": true, "interviewQc": {"status":"pass"}, "buildCompletedAt": "2026-01-01T00:00:00Z", "closeoutStatus": "done", "departments": []}
EOF
HOME="$H_C2b" PATH="$bin_c2b:$PATH" FAKE_OC_JOBS_FILE="$J_C2b" FAKE_OC_CALLS_FILE="$C_C2b" \
  bash "$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" > "$SANDBOX/c2c.log" 2>&1
rc_c2c=$?
sends_c2c=$(grep -c "^message send" "$C_C2b" 2>/dev/null)
[ "$rc_c2c" -eq 0 ] && pass "C2c-rc: resume-workforce-build.sh exits 0 on a terminal/no-work state" || fail "C2c-rc: exited $rc_c2c (expected 0)"
[ "$sends_c2c" -eq 0 ] && pass "C2c: ZERO 'openclaw message send' dispatches (no agent turn triggered) with nothing to resume" \
                        || fail "C2c: $sends_c2c dispatch(es) made with nothing to resume (expected 0)"

# ---------------------------------------------------------------------------
# MUTATION PROOF (C2) — historical agent-message registration would show
# kind=agentTurn instead of command.
# ---------------------------------------------------------------------------
echo ""
echo "--- MUTATION PROOF: reverting to the historical agent-message registration changes kind ---"
MUT_ENSURE="$SANDBOX/ensure-pipeline-crons-mut.sh"
cp "$REPO_ROOT/scripts/ensure-pipeline-crons.sh" "$MUT_ENSURE"
python3 - "$MUT_ENSURE" <<'PYEOF'
import re, sys
path = sys.argv[1]
src = open(path).read()
old = '''  local script
  script="$(_find_script 23-ai-workforce-blueprint scripts/resume-workforce-build.sh)" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP workforce-build-resume — resume-workforce-build.sh not found (older skill bundle)"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "workforce-build-resume" "*/15 * * * *" "$script"; then'''
new = '''  local prompt_file
  prompt_file="$(_find_script 23-ai-workforce-blueprint resume-prompt.txt)" || true
  local prompt="test-mutation-prompt"
  [[ -n "${prompt_file:-}" ]] && prompt="$(cat "$prompt_file" 2>/dev/null || echo test-mutation-prompt)"
  if _oc_cron_silent_main "workforce-build-resume" "main" "*/15 * * * *" "America/New_York" "$prompt" --light-context; then'''
if old not in src:
    print("MUTATION_FAILED: anchor block not found", file=sys.stderr)
    sys.exit(1)
open(path, "w").write(src.replace(old, new, 1))
PYEOF
mut_ok=$?

if [ "$mut_ok" -ne 0 ]; then
  fail "MUT-C2: could not apply the agent-message-revert mutation — cannot prove C2a is discriminating"
else
  Hm="$SANDBOX/home-mut"; binm="$SANDBOX/bin-mut"; Jm="$SANDBOX/jobs-mut.json"; Cm="$SANDBOX/calls-mut.log"
  mkdir -p "$Hm/.openclaw/skills/23-ai-workforce-blueprint/scripts" "$Hm/.openclaw/workspace"
  cp "$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" \
    "$Hm/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
  cp "$REPO_ROOT/23-ai-workforce-blueprint/resume-prompt.txt" \
    "$Hm/.openclaw/skills/23-ai-workforce-blueprint/resume-prompt.txt" 2>/dev/null || true
  _mkbin "$binm"; printf '[]' > "$Jm"; : > "$Cm"
  HOME="$Hm" PATH="$binm:$PATH" FAKE_OC_JOBS_FILE="$Jm" FAKE_OC_CALLS_FILE="$Cm" \
    bash "$MUT_ENSURE" > "$SANDBOX/mut-ensure.log" 2>&1 || true
  kindm=$(python3 -c "
import json
jobs=json.load(open('$Jm'))
m=[j.get('kind','') for j in jobs if j.get('name')=='workforce-build-resume']
print(m[0] if m else 'MISSING')
")
  if [ "$kindm" = "agentTurn" ]; then
    pass "MUT-C2: reverted (mutated) registrar registers workforce-build-resume as kind=agentTurn — proves C2a's kind=='command' assertion is a REAL, non-vacuous check of the command-mode fix"
  else
    fail "MUT-C2: mutated registrar produced kind='$kindm' (expected 'agentTurn') — mutation harness itself may be broken"
  fi
fi

# ---------------------------------------------------------------------------
# C3 — rate-limit/error backoff
# ---------------------------------------------------------------------------
echo ""
echo "--- C3: rate-limit/error backoff widens the next dispatch, no fixed-cadence retry ---"
H_C3="$SANDBOX/home-c3"; bin_c3="$SANDBOX/bin-c3"; J_C3="$SANDBOX/jobs-c3.json"; C_C3="$SANDBOX/calls-c3.log"
mkdir -p "$H_C3/.openclaw/workspace"; _mkbin "$bin_c3"
printf '[]' > "$J_C3"; : > "$C_C3"
cat > "$H_C3/.openclaw/workspace/.workforce-build-state.json" <<'EOF'
{"interviewComplete": true, "interviewQc": {"status":"pass"}, "ownerChat": "999999999", "agentName": "TestAgent", "departments": [{"id":"sales","status":"pending"}], "roleLibraryStatus":"pending", "sopLibraryStatus":"pending"}
EOF
HOME="$H_C3" PATH="$bin_c3:$PATH" FAKE_OC_JOBS_FILE="$J_C3" FAKE_OC_CALLS_FILE="$C_C3" \
  FAKE_OC_MESSAGE_FAIL="error: 429 rate limit exceeded" \
  bash "$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" > "$SANDBOX/c3-run1.log" 2>&1

RL_FILE="$H_C3/.openclaw/workspace/.workforce-build-resume-ratelimit.json"
if [ -f "$RL_FILE" ]; then
  fails_c3=$(python3 -c "import json; print(json.load(open('$RL_FILE')).get('consecutiveFailures', 0))" 2>/dev/null || echo 0)
  [ "$fails_c3" -ge 1 ] && pass "C3a: a 429 dispatch failure wrote a rate-limit backoff marker (consecutiveFailures=$fails_c3)" \
                         || fail "C3a: backoff marker exists but consecutiveFailures=$fails_c3 (expected >=1)"
else
  fail "C3a: no rate-limit backoff marker written after a 429 dispatch failure"
fi

sends_after_run1=$(grep -c "^message send" "$C_C3" 2>/dev/null)

# Clear the lock/inflight so a second fire isn't blocked by THOSE gates
# instead — we want to isolate the rate-limit gate specifically.
rm -f "$H_C3/.openclaw/workspace/.workforce-build-state.lock" \
      "$H_C3/.openclaw/workspace/.workforce-build-resume.inflight" 2>/dev/null || true

HOME="$H_C3" PATH="$bin_c3:$PATH" FAKE_OC_JOBS_FILE="$J_C3" FAKE_OC_CALLS_FILE="$C_C3" \
  FAKE_OC_MESSAGE_FAIL="error: 429 rate limit exceeded" \
  bash "$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" > "$SANDBOX/c3-run2.log" 2>&1
sends_after_run2=$(grep -c "^message send" "$C_C3" 2>/dev/null)

[ "$sends_after_run2" -eq "$sends_after_run1" ] && pass "C3b: an immediate second fire made NO additional dispatch attempt while the backoff window is open ($sends_after_run1 send(s) total, unchanged)" \
                                                  || fail "C3b: second fire added a dispatch attempt ($sends_after_run1 -> $sends_after_run2) — backoff window did not gate the retry"
# NOTE: resume-workforce-build.sh's log() writes to its own state log file
# ($OC_ROOT/workspace/.workforce-build-state.log), NOT to stdout/stderr — the
# captured c3-run2.log is intentionally empty; check the real log target.
STATE_LOG_C3="$H_C3/.openclaw/workspace/.workforce-build-state.log"
grep -qi "RATE-LIMIT BACKOFF" "$STATE_LOG_C3" 2>/dev/null && pass "C3c: run 2 logged the RATE-LIMIT BACKOFF skip explicitly (in $STATE_LOG_C3)" || fail "C3c: run 2 did not log a RATE-LIMIT BACKOFF message in $STATE_LOG_C3"

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all workforce-resume-cheap-command-mode checks pass"
exit 0
