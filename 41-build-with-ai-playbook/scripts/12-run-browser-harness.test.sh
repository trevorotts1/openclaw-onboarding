#!/usr/bin/env bash
# 12-run-browser-harness.test.sh -- negative self-test for the dynamic L1-L5 runner.
# Proves: (a) a clean tree yields publish=PASS exit 0; (b) sabotaging the Big-Brother core so
# L3 mis-classifies yields publish=ESCALATED exit 2 (the loop refuses to publish); (c) the
# emitted qc_result event reflects the escalation. Runs with --no-emit so nothing touches a
# real master-files dir.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # scripts/
RUNNER="$SCRIPT_DIR/12-run-browser-harness.sh"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] 12-run-browser-harness: $1"; exit 1; }

# Skip cleanly on a host with no python3 (L1/L2 SKIP -> runner exit 3 is a WARN, not a bug).
if ! command -v python3 >/dev/null 2>&1; then
  echo "[TEST SKIP] python3 unavailable -- dynamic runner self-test needs the loopback mock"; exit 0
fi

# (a) Clean tree -> PASS, exit 0.
out="$(bash "$RUNNER" --no-emit 2>&1)"; rc=$?
echo "$out" | grep -q 'publish=PASS' || fail "clean tree did not report publish=PASS"
[[ "$rc" -eq 0 ]] || fail "clean tree exit was $rc, expected 0"

# (b) Sabotage the Big-Brother core (rename a detector code) -> L3 meta-check bites ->
#     runner reports ESCALATED + exit 2.
c="$(mktemp -d)"; cp -a "$SKILL_ROOT/." "$c/"
sed -i.bak 's/D1_MISSING_DEPENDENCY/D1_BROKEN_BY_TEST/' "$c/scripts/test/lib-harness.sh"
out2="$(bash "$c/scripts/12-run-browser-harness.sh" --no-emit 2>&1)"; rc2=$?
echo "$out2" | grep -q 'publish=ESCALATED' || { rm -rf "$c"; fail "sabotaged core did not report publish=ESCALATED"; }
line2="$(echo "$out2" | grep -oE '\{.*"event":"qc_result".*\}' | head -1)"
if command -v jq >/dev/null 2>&1; then
  # The escalated qc_result must record publish_decision as a real boolean === false
  # (not the string "ESCALATED"). This is what catches a regression to the old string field.
  echo "$line2" | jq -e '(.publish_decision|type=="boolean") and (.publish_decision==false) and (.escalated_count>=1)' >/dev/null 2>&1 \
    || { rm -rf "$c"; fail "escalated qc_result did not record publish_decision:false (boolean) + escalated_count>=1"; }
fi
[[ "$rc2" -eq 2 ]] || { rm -rf "$c"; fail "sabotaged run exit was $rc2, expected 2"; }
rm -rf "$c"

# (c) The clean qc_result event must be valid JSON matching the f52 contract: the *_count
#     fields are numbers and publish_decision is a REAL boolean (jq type=="boolean") === true.
#     Asserting the names + boolean type is what makes this test CATCH a schema regression.
line="$(echo "$out" | grep -oE '\{.*"event":"qc_result".*\}' | head -1)"
if command -v jq >/dev/null 2>&1; then
  echo "$line" | jq -e '
      (.total|type=="number")
      and (.pass_count|type=="number")
      and (.fixed_count|type=="number")
      and (.escalated_count|type=="number")
      and (.publish_decision|type=="boolean")
      and (.publish_decision==true)
      and (.escalated_count==0)
      and ((.pass_count + .fixed_count)==.total)' >/dev/null 2>&1 \
    || fail "qc_result event does not match f52 contract (*_count numbers + publish_decision boolean true)"
fi

echo "[TEST PASS] 12-run-browser-harness bites (clean=PASS/0+boolean-true, sabotaged core=ESCALATED/2+boolean-false, qc_result matches f52 contract)"
exit 0
