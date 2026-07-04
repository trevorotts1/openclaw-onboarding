#!/usr/bin/env bash
# test-presentation-dept-welcome.sh -- v1.0.0
#
# Dry-run test for the Presentations Department welcome auto-send pipeline.
# Builds a minimal sample .workforce-build-state.json in a temp dir, then
# exercises send-presentation-dept-welcome.sh --dry-run to verify:
#   1. Placeholder resolution works correctly from the sample config.
#   2. The gate check correctly BLOCKS on a non-passing state.
#   3. The gate check correctly PASSES on a fully-passing state.
#   4. Idempotency: a state with presentationDeptWelcomeSent=true triggers
#      early-exit WITHOUT sending (exit 0, no message).
#   5. No client name appears anywhere in the resolved message. The client roster
#      is EXTERNALIZED (see Test 6) so no real name is hardcoded in this test.
#   6. Fallback placeholders work when ownerName/companyName are blank.
#   7. The message body exactly matches the canonical template in
#      templates/role-library/presentations/first-time-onboarding-presentations.md
#      Section 20 (contains all required phrases).
#
# Does NOT send any real Telegram message. Does NOT touch any live box.
# Safe to run in CI or locally.
#
# USAGE:
#   bash test-presentation-dept-welcome.sh
#
# EXIT CODES:
#   0 -- all assertions passed
#   1 -- one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEND_SCRIPT="$SCRIPT_DIR/send-presentation-dept-welcome.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() { echo "  [PASS] $1"; (( PASS_COUNT++ )) || true; }
fail() { echo "  [FAIL] $1" >&2; (( FAIL_COUNT++ )) || true; }

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    pass "$label: contains '$needle'"
  else
    fail "$label: expected '$needle' but not found in output"
  fi
}

assert_not_contains() {
  local label="$1" haystack="$2" needle="$3"
  if ! printf '%s' "$haystack" | grep -qiF "$needle"; then
    pass "$label: does NOT contain '$needle'"
  else
    fail "$label: found forbidden string '$needle' in output"
  fi
}

assert_exit() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" -eq "$expected" ]]; then
    pass "$label: exit code $actual == expected $expected"
  else
    fail "$label: exit code $actual != expected $expected"
  fi
}

echo ""
echo "===================================================================="
echo " test-presentation-dept-welcome.sh -- dry-run test suite"
echo "===================================================================="
echo ""

if [[ ! -f "$SEND_SCRIPT" ]]; then
  echo "[TEST] FATAL: send-presentation-dept-welcome.sh not found at $SEND_SCRIPT" >&2
  exit 1
fi

# ---- build a sample state dir in /tmp ----------------------------------------
# Capture the operator's real HOME before it is redirected to the temp dir, so
# Test 6 can still resolve ~/.openclaw/client-roster.txt (the externalized roster)
# even after HOME is repointed for OC_ROOT resolution.
REAL_HOME="${HOME:-}"
TMPDIR_TEST="$(mktemp -d)"
export HOME="$TMPDIR_TEST"   # redirect OC_ROOT resolution to the temp dir
mkdir -p "$TMPDIR_TEST/.openclaw/workspace"
STATE_FILE="$TMPDIR_TEST/.openclaw/workspace/.workforce-build-state.json"

write_state() {
  local wiring_status="$1" role_lib="$2" sop_lib="$3" already_sent="$4"
  cat > "$STATE_FILE" <<STATEJSON
{
  "version": 1,
  "interviewComplete": true,
  "ownerChat": 9999999999,
  "ownerName": "Sample Owner",
  "companyName": "Sample Business Co",
  "agentName": "Aria",
  "roleLibraryStatus": "done",
  "sopLibraryStatus": "done",
  "departments": [
    {
      "slug": "presentations",
      "name": "Presentations",
      "status": "done",
      "wiringStatus": "$wiring_status",
      "roleLibraryFilled": $role_lib,
      "sopLibraryFilled": $sop_lib,
      "deptHeadPersona": "Sample Dept Head",
      "presentationDeptWelcomeSent": $already_sent
    }
  ]
}
STATEJSON
}

# ==============================================================================
# TEST 1: Gate BLOCKS when wiring not done
# ==============================================================================
echo "--- TEST 1: gate blocks when wiringStatus != done ---"
write_state "pending" "true" "true" "false"
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1) || EXIT1=$?
EXIT1="${EXIT1:-0}"
assert_exit "T1 exit code" "$EXIT1" 2
assert_contains "T1 blocks message" "$OUTPUT" "Gate not yet passed"
echo ""

# ==============================================================================
# TEST 2: Gate BLOCKS when roleLibraryFilled is false
# ==============================================================================
echo "--- TEST 2: gate blocks when roleLibraryFilled=false ---"
write_state "done" "false" "true" "false"
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1) || EXIT2=$?
EXIT2="${EXIT2:-0}"
assert_exit "T2 exit code" "$EXIT2" 2
assert_contains "T2 blocks on roleLib" "$OUTPUT" "Gate not yet passed"
echo ""

# ==============================================================================
# TEST 3: Gate BLOCKS when sopLibraryFilled is false
# ==============================================================================
echo "--- TEST 3: gate blocks when sopLibraryFilled=false ---"
write_state "done" "true" "false" "false"
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1) || EXIT3=$?
EXIT3="${EXIT3:-0}"
assert_exit "T3 exit code" "$EXIT3" 2
assert_contains "T3 blocks on sopLib" "$OUTPUT" "Gate not yet passed"
echo ""

# ==============================================================================
# TEST 4: Idempotency -- presentationDeptWelcomeSent=true triggers early exit
# ==============================================================================
echo "--- TEST 4: idempotency guard (already sent) ---"
write_state "done" "true" "true" "true"
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1)
EXIT4=$?
assert_exit "T4 exit code" "$EXIT4" 0
assert_contains "T4 idempotency msg" "$OUTPUT" "Already sent"
echo ""

# ==============================================================================
# TEST 5: PASS state -- dry-run renders message, fills placeholders correctly
# ==============================================================================
echo "--- TEST 5: full PASS -- dry-run renders message ---"
write_state "done" "true" "true" "false"
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1)
EXIT5=$?
assert_exit "T5 exit code (dry-run pass)" "$EXIT5" 0
assert_contains "T5 gate pass log" "$OUTPUT" "Gate PASSED"
assert_contains "T5 OWNER_FIRST_NAME resolved" "$OUTPUT" "Hi Sample!"
assert_contains "T5 BUSINESS_NAME resolved" "$OUTPUT" "Sample Business Co"
assert_contains "T5 message body: brainstorm" "$OUTPUT" "brainstorm WITH you"
assert_contains "T5 message body: cinematic" "$OUTPUT" "cinematic slide deck"
assert_contains "T5 message body: Presenter's Guide" "$OUTPUT" "Presenter's Guide"
assert_contains "T5 message body: speech" "$OUTPUT" "word-for-word speech"
assert_contains "T5 message body: audio demo" "$OUTPUT" "audio demonstration"
assert_contains "T5 message body: PowerPoint" "$OUTPUT" "PowerPoint and PDF"
# Intake doctrine: choice-first (quick vs in-depth) + ONE question at a time.
assert_contains "T5 intake: choice-first path" "$OUTPUT" "quick or an in-depth path"
assert_contains "T5 intake: one at a time" "$OUTPUT" "one question at a time"
# Banned drift phrase must NEVER reappear in the client-facing welcome (PR-440).
assert_not_contains "T5 no banned 'few quick questions'" "$OUTPUT" "ask a few quick questions"
assert_contains "T5 dry-run label" "$OUTPUT" "DRY-RUN complete"
echo ""

# ==============================================================================
# TEST 6: Anti-commingling -- no hardcoded client names in resolved message
# ==============================================================================
# The client roster is EXTERNALIZED to an operator-local, gitignored file
# ($OPENCLAW_CLIENT_ROSTER or ~/.openclaw/client-roster.txt; template
# scripts/client-roster.example.txt) so no real client name is hardcoded here.
# When the roster is absent (e.g. CI) the roster-specific loop is SKIPPED with a
# WARNING, but the .example-placeholder assertions STILL run so the test never
# fails open. NOTE: assert_not_contains resets HOME below via write_state's
# `export HOME`, so resolve the roster path BEFORE that export changes HOME.
echo "--- TEST 6: anti-commingling -- no hardcoded client names ---"
_pres_roster_path() {
  if [ -n "${OPENCLAW_CLIENT_ROSTER:-}" ]; then printf '%s\n' "$OPENCLAW_CLIENT_ROSTER"
  else printf '%s\n' "${REAL_HOME:-${HOME:-/root}}/.openclaw/client-roster.txt"; fi
}
write_state "done" "true" "true" "false"
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1)
# Always-on: the obviously-fake roster-template placeholders must never render.
for PLACEHOLDER in ExampleClientAlpha ExampleClientBeta PlaceholderCo "Testclient Sentinel"; do
  assert_not_contains "T6 no placeholder '$PLACEHOLDER'" "$OUTPUT" "$PLACEHOLDER"
done
# Roster-specific: load real client names (if the roster is present) and assert
# none leaked into the resolved message. Strip \b anchors for fixed-string match.
_PRES_ROSTER="$(_pres_roster_path)"
if [ -f "$_PRES_ROSTER" ]; then
  while IFS= read -r _rline; do
    case "$_rline" in ''|\#*) continue ;; esac
    _needle="${_rline//\\b/}"
    [ -n "$_needle" ] || continue
    assert_not_contains "T6 no client '$_needle'" "$OUTPUT" "$_needle"
  done < <(grep -vE '^[[:space:]]*(#|$)' "$_PRES_ROSTER")
else
  echo "  [WARN] client-name roster not found (looked in \$OPENCLAW_CLIENT_ROSTER, then $_PRES_ROSTER); SKIPPING the roster-specific anti-commingling check. Placeholder checks still ran. See scripts/client-roster.example.txt." >&2
fi
echo ""

# ==============================================================================
# TEST 7: Fallback placeholders when ownerName/companyName are blank
# ==============================================================================
echo "--- TEST 7: fallback placeholders when fields are blank ---"
cat > "$STATE_FILE" <<STATEJSON
{
  "version": 1,
  "interviewComplete": true,
  "ownerChat": 9999999999,
  "ownerName": "",
  "companyName": "",
  "departments": [
    {
      "slug": "presentations",
      "name": "Presentations",
      "status": "done",
      "wiringStatus": "done",
      "roleLibraryFilled": true,
      "sopLibraryFilled": true,
      "presentationDeptWelcomeSent": false
    }
  ]
}
STATEJSON
OUTPUT=$(bash "$SEND_SCRIPT" --dry-run 2>&1)
EXIT7=$?
assert_exit "T7 exit code" "$EXIT7" 0
assert_contains "T7 fallback owner" "$OUTPUT" "Hi there!"
assert_contains "T7 fallback business" "$OUTPUT" "your business"
echo ""

# ---- cleanup -----------------------------------------------------------------
rm -rf "$TMPDIR_TEST"

# ---- summary -----------------------------------------------------------------
echo "===================================================================="
echo " RESULTS: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "===================================================================="
echo ""

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  echo "[test-presentation-dept-welcome] FAIL: $FAIL_COUNT assertion(s) failed." >&2
  exit 1
fi

echo "[test-presentation-dept-welcome] All assertions passed."
exit 0
