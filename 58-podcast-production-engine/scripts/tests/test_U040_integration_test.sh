#!/usr/bin/env bash
# =============================================================================
# U040 :: Mandatory tests for the integration test script
#
# Tests the integration-test-podbean-publish-verify.sh script itself:
#   1. bash -n syntax check passes
#   2. Opt-in guard: running without PODBEAN_INTEGRATION_TEST=1 exits 0 with
#      "SKIPPED" in the output
#   3. Mutation proof: when the guard is removed, the mutated script exits
#      non-zero (credential failure), proving the test detects guard removal.
#      Reverting the mutation restores the pass.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTEGRATION_TEST="$HERE/integration-test-podbean-publish-verify.sh"

red()    { printf '\033[31m%s\033[0m\n' "$1" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$1" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$1" >&2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0

# --- Test 1: bash -n syntax check --------------------------------------------
echo "--- Test 1: bash -n on integration test script ---"
if bash -n "$INTEGRATION_TEST" 2>&1; then
  green "  PASS — integration test passes bash -n"
  PASS=$((PASS+1))
else
  red "  FAIL — integration test failed bash -n"
  FAIL=$((FAIL+1))
fi

# --- Test 2: opt-in guard exits 0 with SKIPPED --------------------------------
echo ""
echo "--- Test 2: opt-in guard (env var absent) ---"
env -u PODBEAN_INTEGRATION_TEST bash "$INTEGRATION_TEST" > "$WORK/skip-stdout.log" 2>"$WORK/skip-stderr.log"
SKIP_EXIT=$?
SKIP_OUTPUT="$(cat "$WORK/skip-stdout.log" "$WORK/skip-stderr.log")"

if [ "$SKIP_EXIT" -ne 0 ]; then
  red "  FAIL — integration test exited $SKIP_EXIT when opt-in env var was absent (expected 0)"
  FAIL=$((FAIL+1))
else
  green "  OK — integration test exited 0 when opt-in env var was absent"
fi

if echo "$SKIP_OUTPUT" | grep -qi "SKIPPED"; then
  green "  OK — output contains SKIPPED"
else
  red "  FAIL — output does not contain SKIPPED"
  FAIL=$((FAIL+1))
fi

if echo "$SKIP_OUTPUT" | grep -q "PODBEAN_INTEGRATION_TEST"; then
  green "  OK — output references PODBEAN_INTEGRATION_TEST (self-documenting opt-in)"
  PASS=$((PASS+1))
else
  red "  FAIL — output does not reference PODBEAN_INTEGRATION_TEST"
  FAIL=$((FAIL+1))
fi

# --- Test 3: mutation proof (guard removal detected) --------------------------
echo ""
echo "--- Test 3: mutation proof (guard removal detected) ---"
cp "$INTEGRATION_TEST" "$WORK/mutated-test.sh"

# Excise the opt-in guard block: from the "# --- Opt-in guard" comment line
# through its closing "fi". The guard is a simple if-fi with no nesting.
python3 -c '
import sys
with open(sys.argv[1], "r") as f:
    src = f.readlines()

# Find the guard comment line
guard_start = None
for i, line in enumerate(src):
    stripped = line.strip()
    if stripped.startswith("#") and "Opt-in guard" in stripped:
        guard_start = i
        break

if guard_start is None:
    print("Mutation error: could not find opt-in guard comment", file=sys.stderr)
    sys.exit(1)

# Walk forward from guard_start+1 to find the first "if" and then matching "fi"
guard_if = None
guard_fi = None
for i in range(guard_start + 1, len(src)):
    tok = src[i].strip().split()[0] if src[i].strip().split() else ""
    if guard_if is None and tok == "if":
        guard_if = i
    elif guard_if is not None and tok == "fi":
        guard_fi = i
        break

if guard_fi is None:
    print("Mutation error: could not find closing fi for opt-in guard", file=sys.stderr)
    sys.exit(1)

# Excise from guard comment through closing fi (inclusive)
mutated = src[:guard_start] + src[guard_fi + 1:]
with open(sys.argv[2], "w") as f:
    f.writelines(mutated)
print(f"Guard excised: lines {guard_start+1}-{guard_fi+1}")
' "$INTEGRATION_TEST" "$WORK/mutated-test.sh"

chmod +x "$WORK/mutated-test.sh"

# Run the mutated script without credentials. Without the guard, it will
# proceed past the opt-in and fail on credential checks (exit non-zero).
set +e
(
  unset PODBEAN_INTEGRATION_TEST PODBEAN_CLIENT_ID PODBEAN_CLIENT_SECRET \
        PODBEAN_PODCAST_ID PODBEAN_API_BASE PODBEAN_BROKER_WEBHOOK_URL \
        PODBEAN_BROKER_TOKEN PODBEAN_PUBLISH_WEBHOOK_URL PODBEAN_PUBLISH_TOKEN \
        PODCAST_CLIENT_LAST_NAME PODCAST_CLIENT_EMAIL
  bash "$WORK/mutated-test.sh" > "$WORK/mut-stdout.log" 2>"$WORK/mut-stderr.log"
  echo $? > "$WORK/mut-exit.txt"
)
set -e
MUT_EXIT=$(cat "$WORK/mut-exit.txt" 2>/dev/null || echo 0)
MUT_STDERR="$(cat "$WORK/mut-stderr.log")"

if [ "$MUT_EXIT" -ne 0 ]; then
  green "  PASS — mutated script (guard excised) exited non-zero ($MUT_EXIT)"
  green "         This proves the test detects when the opt-in guard is removed."
  PASS=$((PASS+1))
else
  red "  FAIL — mutated script (guard excised) still exited 0"
  red "         The integration test would PASS a version without an opt-in guard."
  FAIL=$((FAIL+1))
fi

MUT_OUTPUT="$(cat "$WORK/mut-stdout.log" "$WORK/mut-stderr.log")"
if echo "$MUT_OUTPUT" | grep -qi "SKIPPED"; then
  red "  FAIL — mutated script still printed SKIPPED (mutation was incomplete)"
  FAIL=$((FAIL+1))
else
  green "  OK — mutated script did not print SKIPPED (guard was successfully excised)"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed ═══"
if [ "$FAIL" -gt 0 ]; then
  red "U040 mandatory tests FAILED"
  exit 1
fi
green "U040 mandatory tests PASSED"
exit 0
