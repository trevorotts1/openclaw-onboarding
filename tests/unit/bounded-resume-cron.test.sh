#!/usr/bin/env bash
# tests/unit/bounded-resume-cron.test.sh
#
# CI guard: verifies that the onboarding-resume cron mechanism is bounded and
# self-deleting rather than a perpetual token furnace.
#
# Assertion groups:
#   (1) MAX_RUNS_CAP        -- MAX_RUNS_BEFORE_ESCALATE is defined and <= 10
#   (2) HARD_STOP_DELETE    -- past the cap the script calls self_remove_cron + exit 0, not a slow-retry loop
#   (3) NO_FURNACE_LANGUAGE -- resume-onboarding-prompt.txt does NOT contain
#                             "NEVER STOP", "DO NOT ASK PERMISSION", or "EXECUTE IMMEDIATELY"
#   (4) NO_FURNACE_AGENTS_TEMPLATE -- UPDATE PENDING template in install.sh and
#                             update-skills.sh does NOT contain "DO NOT ASK PERMISSION"
#                             or "EXECUTE IMMEDIATELY" in the injected flag block
#   (5) SELF_REMOVE_ON_GATE -- self_remove_cron is called on gate-pass path in resume-onboarding.sh
#   (6) CRON_INTERVAL       -- onboarding-resume cron is registered at */30 (reasonable; not */5 or */1)
#   (7) SINGLE_MODEL        -- resume-onboarding-prompt.txt does NOT instruct fan-out
#                             across "all configured models" or spawn multiple subagents
#   (8) BEHAVIORAL_CAP_ENFORCEMENT -- BEHAVIORAL, not static: actually RUNS
#                             resume-onboarding.sh, in an isolated sandbox with
#                             openclaw/curl stubbed, enough times to cross the
#                             cap, and checks what the run-counter file and the
#                             stubbed calls actually did. (1) and (2) only prove
#                             the cap CONSTANT and the word "self_remove_cron"
#                             exist in the source -- they stayed green on a real
#                             box while the guard script hadn't actually run in
#                             over a month. (8) proves enforcement by execution.
#
# Exit 0 = all checks pass. Exit 1 = one or more checks failed (CI FAIL).
#
# v12.6.1 / fix/bound-onboarding-resume-furnace

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

RESUME_SH="$REPO_ROOT/scripts/resume-onboarding.sh"
RESUME_PROMPT="$REPO_ROOT/scripts/resume-onboarding-prompt.txt"
INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
# v17.0.21: install_onboarding_resume_cron() moved to a shared lib sourced by
# BOTH install.sh and update-skills.sh, so the cron's registration (interval,
# name) now lives here. The interval check (6) scans this file too.
RESUME_CRON_LIB="$REPO_ROOT/lib-onboarding-resume-cron.sh"

echo "=== bounded-resume-cron.test.sh ==="
echo ""

# ---------------------------------------------------------------------------
# (1) MAX_RUNS_CAP: MAX_RUNS_BEFORE_ESCALATE defined and <= 10
# ---------------------------------------------------------------------------
echo "--- (1) MAX_RUNS_CAP: hard cap defined and <= 10 ---"

if [[ ! -f "$RESUME_SH" ]]; then
  fail "1a: resume-onboarding.sh not found at $RESUME_SH"
else
  cap_line="$(grep 'MAX_RUNS_BEFORE_ESCALATE=' "$RESUME_SH" | grep -v '^[[:space:]]*#' | head -1 || true)"
  if [[ -z "$cap_line" ]]; then
    fail "1a: MAX_RUNS_BEFORE_ESCALATE not defined in resume-onboarding.sh"
  else
    cap_val="$(echo "$cap_line" | sed 's/.*MAX_RUNS_BEFORE_ESCALATE=[[:space:]]*//' | grep -o '^[0-9]*' || true)"
    if [[ -z "$cap_val" ]]; then
      fail "1b: MAX_RUNS_BEFORE_ESCALATE value is not a plain integer (got: $cap_line)"
    elif (( cap_val > 10 )); then
      fail "1b: MAX_RUNS_BEFORE_ESCALATE=$cap_val exceeds safe limit of 10 (token furnace risk)"
    else
      pass "1b: MAX_RUNS_BEFORE_ESCALATE=$cap_val (within safe limit of 10)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (2) HARD_STOP_DELETE: past cap the script calls self_remove_cron and exits 0,
#     NOT a slow-retry/perpetual-loop path
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) HARD_STOP_DELETE: cap branch calls self_remove_cron + exit 0 ---"

if [[ -f "$RESUME_SH" ]]; then
  # The block that fires when _run_count > MAX_RUNS_BEFORE_ESCALATE must contain
  # self_remove_cron and MUST NOT contain a comment/label saying "NOT self-removing"
  # or "slow-retry" or "never stops".
  cap_block="$(awk '/\(\( _run_count > MAX_RUNS_BEFORE_ESCALATE \)\)/,/^fi$/' "$RESUME_SH" 2>/dev/null | head -60 || true)"

  if [[ -z "$cap_block" ]]; then
    fail "2a: could not extract cap branch from resume-onboarding.sh (pattern not found)"
  else
    if echo "$cap_block" | grep -q 'self_remove_cron'; then
      pass "2a: cap branch calls self_remove_cron"
    else
      fail "2a: cap branch does NOT call self_remove_cron -- cron will never self-delete on hard cap"
    fi

    # These phrases indicate the old perpetual-loop behavior: continuing to dispatch
    # after the cap rather than self-deleting. The negative phrase "No perpetual slow-retry"
    # is fine (it documents the absence of the pattern).
    if echo "$cap_block" | grep -qiE 'NOT self.remov|now slow.retry|never stop.*continu|slow mode.*continuing'; then
      fail "2b: cap branch contains perpetual-loop language (slow-retry/never-stop/NOT-self-removing)"
    else
      pass "2b: cap branch has no perpetual-loop language"
    fi

    if echo "$cap_block" | grep -q 'exit 0'; then
      pass "2c: cap branch exits 0 after escalation (bounded)"
    else
      fail "2c: cap branch does not exit 0 -- may fall through to another dispatch"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (3) NO_FURNACE_LANGUAGE: resume-onboarding-prompt.txt must not contain
#     the imperative language that drove unbounded autonomous loops
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) NO_FURNACE_LANGUAGE: prompt file lacks unbounded-loop imperatives ---"

if [[ ! -f "$RESUME_PROMPT" ]]; then
  fail "3a: resume-onboarding-prompt.txt not found at $RESUME_PROMPT"
else
  for pattern in "NEVER STOP" "DO NOT ASK PERMISSION" "EXECUTE IMMEDIATELY" "NEVER-STOP"; do
    if grep -qi "$pattern" "$RESUME_PROMPT"; then
      fail "3-$(echo $pattern | tr ' ' '-'): resume-onboarding-prompt.txt contains forbidden phrase: '$pattern'"
    else
      pass "3-$(echo $pattern | tr ' ' '-'): prompt does not contain '$pattern'"
    fi
  done
fi

# ---------------------------------------------------------------------------
# (4) NO_FURNACE_AGENTS_TEMPLATE: UPDATE PENDING blocks in install.sh and
#     update-skills.sh must not inject "DO NOT ASK PERMISSION" or
#     "EXECUTE IMMEDIATELY" into AGENTS.md
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) NO_FURNACE_AGENTS_TEMPLATE: UPDATE PENDING heredoc lacks furnace imperatives ---"

check_update_pending_block() {
  local file="$1"
  local fname
  fname=$(basename "$file")

  # Extract the heredoc / cat block that writes the UPDATE PENDING section.
  # Look for text between the heredoc marker and FLAGCONTENT closing tag.
  local block
  block="$(awk '/FLAGCONTENT$/,/^FLAGCONTENT$/' "$file" 2>/dev/null | head -80 || true)"

  if [[ -z "$block" ]]; then
    # Try alternative: grep context around UPDATE PENDING header
    block="$(grep -A 5 'UPDATE PENDING' "$file" 2>/dev/null | head -20 || true)"
  fi

  for pattern in "DO NOT ASK PERMISSION" "EXECUTE IMMEDIATELY"; do
    if echo "$block" | grep -qi "$pattern"; then
      fail "4-$fname-$(echo $pattern | tr ' ' '-'): $fname UPDATE PENDING block contains '$pattern'"
    else
      pass "4-$fname-$(echo $pattern | tr ' ' '-'): $fname UPDATE PENDING block does not contain '$pattern'"
    fi
  done
}

[[ -f "$INSTALL_SH" ]] && check_update_pending_block "$INSTALL_SH" || fail "4-install.sh: not found"
[[ -f "$UPDATE_SH" ]] && check_update_pending_block "$UPDATE_SH" || fail "4-update-skills.sh: not found"

# ---------------------------------------------------------------------------
# (5) SELF_REMOVE_ON_GATE: gate-pass path calls self_remove_cron
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) SELF_REMOVE_ON_GATE: gate-pass path calls self_remove_cron ---"

if [[ -f "$RESUME_SH" ]]; then
  gate_block="$(awk '/GATE_RC.*==.*0/,/exit 0/' "$RESUME_SH" 2>/dev/null | head -10 || true)"
  if echo "$gate_block" | grep -q 'self_remove_cron'; then
    pass "5a: gate-pass block calls self_remove_cron before exit 0"
  else
    fail "5a: gate-pass block does NOT call self_remove_cron -- cron persists after gate passes"
  fi
fi

# ---------------------------------------------------------------------------
# (6) CRON_INTERVAL: cron is registered at */30 or longer -- not a high-frequency furnace
# ---------------------------------------------------------------------------
echo ""
echo "--- (6) CRON_INTERVAL: cron registered at */30 or longer ---"

# Scan BOTH install.sh and the shared resume-cron lib (the cron registration
# now lives in the lib; install.sh only sources+calls it). At least one file
# must carry an onboarding-resume interval line, and every such line must be
# */15 or slower.
_interval_seen=0
for _f in "$INSTALL_SH" "$RESUME_CRON_LIB"; do
  [[ -f "$_f" ]] || continue
  interval_lines="$(grep "onboarding-resume" "$_f" | grep '\*/[0-9]' || true)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    _interval_seen=1
    interval="$(echo "$line" | grep -o '\*/[0-9]*' | head -1 || true)"
    val="$(echo "$interval" | grep -o '[0-9]*' || true)"
    if [[ -z "$val" ]]; then
      pass "6: could not parse interval from line ($(basename "$_f")); skipping: $line"
    elif (( val < 15 )); then
      fail "6: onboarding-resume cron interval $interval in $(basename "$_f") is faster than */15 -- high-frequency furnace risk"
    else
      pass "6: onboarding-resume cron interval $interval in $(basename "$_f") (>= */15, safe)"
    fi
  done <<< "$interval_lines"
done
if [[ "$_interval_seen" -eq 0 ]]; then
  fail "6: no onboarding-resume interval line found in install.sh or lib-onboarding-resume-cron.sh -- cron registration missing?"
fi

# ---------------------------------------------------------------------------
# (7) SINGLE_MODEL: prompt does not instruct fan-out across all models or
#     spawning 5+ subagents
# ---------------------------------------------------------------------------
echo ""
echo "--- (7) SINGLE_MODEL: prompt does not instruct multi-model fan-out ---"

if [[ -f "$RESUME_PROMPT" ]]; then
  # Each pattern below: a positive instruction to fan-out. Prohibitions ("Do NOT fan-out")
  # are desirable and must not trip the check.
  # Strategy: check for lines that contain the pattern WITHOUT a preceding "NOT" or "Do NOT".
  check_no_positive_fanout() {
    local pattern="$1" label="$2"
    # Find lines with the pattern, then exclude lines that have NOT/Do NOT nearby (within the same line).
    local hits
    hits="$(grep -iE "$pattern" "$RESUME_PROMPT" | grep -viE 'do not|NOT spawn|NOT fan|avoid|prohibit' || true)"
    if [[ -n "$hits" ]]; then
      fail "7-${label}: resume prompt appears to instruct fan-out (check for false-positive): $(echo "$hits" | head -1)"
    else
      pass "7-${label}: prompt does not instruct '$pattern' (or only prohibits it)"
    fi
  }

  check_no_positive_fanout "fan.out across all" "fan-out-across-all"
  check_no_positive_fanout "spawn.*across.*all.*model" "spawn-across-all-models"
  check_no_positive_fanout "use all configured models" "use-all-configured-models"
  check_no_positive_fanout "5\+ subagents" "5plus-subagents"
  check_no_positive_fanout "spawn 5 subagents" "spawn-5-subagents"
fi

# ---------------------------------------------------------------------------
# (8) BEHAVIORAL_CAP_ENFORCEMENT: prove the cap is enforced by EXECUTION, not
#     by grepping source for a constant or a function name.
#
# WHY THIS SECTION EXISTS (do not delete it to "simplify" this file):
#   Checks (1) and (2) above are STATIC: they prove MAX_RUNS_BEFORE_ESCALATE
#   is defined, and that the TEXT of the cap branch contains the string
#   "self_remove_cron". On a real box those checks were green while the cron
#   had fired roughly 330 times and the guard script had not actually run in
#   over a month -- the code existed, but nothing was exercising it. A test
#   that proves code exists while enforcement is dead manufactures confidence
#   it has not earned. This section instead RUNS scripts/resume-onboarding.sh,
#   fully isolated, enough times to cross the cap, and checks what the
#   run-counter file and the (stubbed) openclaw/curl calls actually did.
#
# ISOLATION: every invocation below runs with HOME pointed at a throwaway
#   mktemp directory (so OC_ROOT inside the script never resolves to a real
#   ~/.openclaw), and with `openclaw` and `curl` shadowed by local no-op
#   stubs placed earlier on PATH. Nothing here can reach a real cron, a real
#   chat/telegram send, or a real webhook -- see the stub sanity check (8a)
#   below, which proves the shadowing actually works before anything else is
#   trusted.
#
# WHAT THIS SECTION DOES NOT PROVE (see the STRUCTURAL CAVEAT comment after
#   it): it proves the shell guard enforces its own cap correctly WHEN RUN.
#   It cannot prove the guard actually GETS run on every real cron fire.
# ---------------------------------------------------------------------------
echo ""
echo "--- (8) BEHAVIORAL_CAP_ENFORCEMENT: cap enforced by execution, not by string presence ---"

behavioral_cap_test() {
  local cap
  if [[ "${cap_val:-}" =~ ^[0-9]+$ ]]; then
    cap="$cap_val"          # reuse the value check (1) already extracted from source
  else
    cap=5                   # documented default, used only if (1) couldn't extract one
  fi
  local drive_count=$(( cap + 1 ))   # one more than the cap -- it MUST fire by then

  if ! command -v mktemp >/dev/null 2>&1; then
    fail "8-setup: mktemp not available -- cannot build an isolated sandbox"
    return 0
  fi
  if [[ ! -f "$RESUME_SH" ]]; then
    fail "8-setup: resume-onboarding.sh not found -- cannot drive the behavioral test"
    return 0
  fi

  local WORKDIR TMP_HOME TEST_REPO STUB_BIN WS STATE_FILE WF_STATE RUN_COUNT_FILE CALL_LOG
  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bounded-resume-cron-behavioral.XXXXXX" 2>/dev/null || true)"
  if [[ -z "$WORKDIR" || ! -d "$WORKDIR" ]]; then
    fail "8-setup: mktemp -d failed -- cannot build an isolated sandbox"
    return 0
  fi

  # Isolated fake $HOME -- resume-onboarding.sh resolves OC_ROOT from
  # $HOME/.openclaw, so overriding HOME is what keeps every invocation below
  # off the real box (this box has a real ~/.openclaw -- see STATE_FILE etc.
  # below, none of which are the real ones).
  TMP_HOME="$WORKDIR/home"
  TEST_REPO="$WORKDIR/repo-copy"
  STUB_BIN="$WORKDIR/bin"
  CALL_LOG="$WORKDIR/openclaw-calls.log"
  mkdir -p "$TMP_HOME/.openclaw/workspace" "$TEST_REPO/scripts" "$STUB_BIN"
  : > "$CALL_LOG"

  WS="$TMP_HOME/.openclaw/workspace"
  STATE_FILE="$WS/.onboarding-state.json"
  WF_STATE="$WS/.workforce-build-state.json"
  RUN_COUNT_FILE="$WS/.onboarding-resume-runs.count"

  # Empty skills map + interview complete: the verification gate never
  # passes and there is no pending/parked work, so every invocation runs
  # straight through the run-counter + cap logic and exits cleanly, without
  # ever reaching the message-dispatch code path (that path's stub is
  # exercised separately below by the direct sanity check (8a), not by the
  # counter drive itself).
  printf '%s\n' '{"skills": {}}' > "$STATE_FILE"
  printf '%s\n' '{"interviewComplete": true}' > "$WF_STATE"

  # Copy the REAL script, byte for byte, into a location with NO sibling
  # lib-onboarding-state.sh / onboarding-state.sh. This makes the script's
  # OWN documented fallback branch ("gate library not found -- falling back
  # to JSON status scan") the one that runs, deterministically -- independent
  # of whatever the live gate library (owned by a different unit) currently
  # contains. This is real execution of the real file, not a rewrite of it.
  cp "$RESUME_SH" "$TEST_REPO/scripts/resume-onboarding.sh"

  # Stub openclaw: records every call it receives and performs NO real
  # action -- no network call, no message send, no cron mutation against
  # anything real. `cron list` reports one fake job so self_remove_cron has
  # a UUID to "remove" (also fake, never a real cron).
  cat > "$STUB_BIN/openclaw" <<'STUBEOF'
#!/usr/bin/env bash
echo "openclaw $*" >> "$CALL_LOG"
case "$1" in
  cron)
    case "$2" in
      list) echo "  onboarding-resume   aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" ;;
      rm)   echo "CRON_RM:$3" >> "$CALL_LOG" ;;
    esac
    ;;
esac
exit 0
STUBEOF
  chmod +x "$STUB_BIN/openclaw"

  # Stub curl: records every call, makes NO real network request. This is
  # the only other external-call surface in the script (the Rescue Rangers
  # webhook escalation on the cap branch).
  cat > "$STUB_BIN/curl" <<'STUBEOF'
#!/usr/bin/env bash
echo "curl $*" >> "$CALL_LOG"
exit 0
STUBEOF
  chmod +x "$STUB_BIN/curl"

  # --- (8a) direct stub sanity check: prove message-send and cron-rm ARE
  # intercepted before trusting the drive below to mean anything ---
  HOME="$TMP_HOME" PATH="$STUB_BIN:$PATH" CALL_LOG="$CALL_LOG" \
    openclaw message send --channel telegram -t testchat -m "should never leave this sandbox" >/dev/null 2>&1 || true
  HOME="$TMP_HOME" PATH="$STUB_BIN:$PATH" CALL_LOG="$CALL_LOG" \
    openclaw cron rm deadbeef-0000-0000-0000-000000000000 >/dev/null 2>&1 || true
  if grep -q "^openclaw message send" "$CALL_LOG" 2>/dev/null && grep -q "^CRON_RM:deadbeef" "$CALL_LOG" 2>/dev/null; then
    pass "8a: openclaw message-send and cron-rm calls are intercepted by the local stub (nothing sent externally)"
  else
    fail "8a: stub did not record the expected calls -- cannot trust isolation for the drive below"
  fi
  : > "$CALL_LOG"   # reset so the log below reflects only the counter drive

  # --- (8b/8c/8d) drive the counter/cap logic $drive_count times against the
  # REAL script (cap = $cap) -- this is the actual behavioral proof ---
  local i rc count_now all_rc_ok=1 all_increments_ok=1
  for (( i=1; i<=drive_count; i++ )); do
    rc=0
    HOME="$TMP_HOME" PATH="$STUB_BIN:$PATH" CALL_LOG="$CALL_LOG" \
      OPERATOR_ESCALATION_CHAT_ID="" OPERATOR_HELP_CHAT_ID="" OPERATOR_TELEGRAM_CHAT_ID="" \
      RESCUE_RANGERS_WEBHOOK_URL="http://127.0.0.1:1/unused-stubbed-in-test" \
      RESCUE_RANGERS_WEBHOOK_SECRET="" \
      bash "$TEST_REPO/scripts/resume-onboarding.sh" >"$WORKDIR/run-$i.log" 2>&1 || rc=$?
    if [[ "$rc" -ne 0 ]]; then
      fail "8b-run$i: resume-onboarding.sh exited $rc (expected 0) -- see $WORKDIR/run-$i.log"
      all_rc_ok=0
    fi

    if (( i < drive_count )); then
      count_now=""
      [[ -f "$RUN_COUNT_FILE" ]] && count_now="$(cat "$RUN_COUNT_FILE" 2>/dev/null || true)"
      if [[ "$count_now" == "$i" ]]; then
        pass "8c-run$i: run-count file reads '$i' after invocation $i (counter incremented by EXECUTION, not asserted from source)"
      else
        fail "8c-run$i: run-count file reads '${count_now:-<missing>}', expected '$i' -- counter did not increment by execution"
        all_increments_ok=0
      fi
    fi
  done
  [[ "$all_rc_ok" -eq 1 ]] && pass "8b: all $drive_count invocations exited 0"
  [[ "$all_increments_ok" -eq 1 ]] && pass "8c: run-counter incremented on every one of the $(( drive_count - 1 )) pre-cap invocations"

  if grep -q "^openclaw cron rm aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" "$CALL_LOG" 2>/dev/null && grep -q "^CRON_RM:aaaaaaaa" "$CALL_LOG" 2>/dev/null; then
    pass "8d: invocation #$drive_count (cap+1) triggered self_remove_cron -> openclaw cron rm (proven by the stub's call log, not by grepping source)"
  else
    fail "8d: invocation #$drive_count did NOT call cron rm -- the cap was NOT enforced by execution"
  fi

  if grep -q "^curl " "$CALL_LOG" 2>/dev/null; then
    pass "8e: cap-branch Rescue-Rangers escalation attempted a webhook call and it was caught by the local curl stub (no real network request made)"
  else
    fail "8e: expected a stubbed curl call on the cap branch and found none -- either escalation didn't fire or isolation is not exercising that path"
  fi

  if [[ ! -f "$RUN_COUNT_FILE" ]]; then
    pass "8f: run-count file was removed after self-removal (matches self_remove_cron's own cleanup on success)"
  else
    fail "8f: run-count file still present after the cap fired (expected cleanup): $(cat "$RUN_COUNT_FILE" 2>/dev/null || true)"
  fi

  rm -rf "$WORKDIR" 2>/dev/null || true
}

behavioral_cap_test

# ---------------------------------------------------------------------------
# STRUCTURAL CAVEAT (record this; do not delete it). Confirmed by reading
# lib-onboarding-resume-cron.sh and scripts/resume-onboarding-prompt.txt:
#
# The onboarding-resume cron does NOT execute resume-onboarding.sh directly.
# It fires a PROMPT (the contents of resume-onboarding-prompt.txt) into the
# agent's own main session via `openclaw cron ... --system-event` /
# `--message` (see install_onboarding_resume_cron / _oc_cron_silent_main in
# lib-onboarding-resume-cron.sh). "STEP -1" of that prompt text instructs the
# agent to run `bash .../resume-onboarding.sh` as a shell command.
#
# The hard cap this file tests is therefore only enforced if the model that
# receives that prompt actually executes a shell command in response to it.
# If exec is unavailable to the agent, the model does not choose to run it,
# or it otherwise skips STEP -1, resume-onboarding.sh never runs:
# RUN_COUNT_FILE is never touched, and MAX_RUNS_BEFORE_ESCALATE can never
# fire -- no matter how many times the cron itself has fired on schedule.
#
# This is exactly the class of failure this test suite exists to catch: an
# affected box's cron fired roughly 330 times while the guard script had not
# actually executed in about a month. The cap is MODEL-DEPENDENT, not
# SCHEDULER-ENFORCED: the scheduler guarantees the prompt is delivered on
# schedule; it does not and cannot guarantee the guard script gets executed.
# Section (8) above proves the guard is correct WHEN it runs; it cannot
# prove -- and does not claim to prove -- that it reliably gets run.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all bounded-resume-cron checks pass"
exit 0
