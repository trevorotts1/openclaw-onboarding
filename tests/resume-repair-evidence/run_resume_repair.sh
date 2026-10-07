#!/bin/sh
# run_resume_repair.sh: run every W4-03-U1 resume/repair evidence test,
# print a summary table, exit non-zero on any failure.
# Suite writes only into tests/resume-repair-evidence/evidence/ plus its own
# /tmp/lane-W4-03-U1-* scratch (removed by each test in a finally block).
cd "$(dirname "$0")" || exit 2
LANE=${DTS_BUILD_ROOT}/swarm-plans/lanes/W4-03-U1-lane
mkdir -p "$LANE"
pass=0; fail=0; failed=""; rows=""
for t in test_*.py; do
  if python3 "$t" > "$LANE/$t.log" 2>&1; then
    pass=$((pass+1)); rows="$rows
  $t  PASS  $(tail -1 "$LANE/$t.log")"
  else
    fail=$((fail+1)); failed="$failed $t"
    rows="$rows
  $t  FAIL  (see $LANE/$t.log)"
  fi
done
echo "=== W4-03-U1 resume-repair-evidence summary ==="
echo "  file  result  detail$rows"
echo "  pass=$pass fail=$fail"
echo "  evidence: tests/resume-repair-evidence/evidence/"
echo "  lane logs: $LANE"
[ "$fail" -eq 0 ] || { echo "FAILED:$failed"; exit 1; }
echo ALL_RESUME_REPAIR_TESTS_PASS
