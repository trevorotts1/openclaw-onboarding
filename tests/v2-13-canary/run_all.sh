#!/bin/sh
# run_all.sh: drive the V2-13 lip-sync model-quality canary suite (BO-LIP-R-U2).
#
# Families: spec roster order, closed two-entry provider set, shot bounds,
#           scripted primary path, scripted fallback path, both-fail path,
#           attempt-order refusal, zero-spend / no-network hygiene,
#           live entrypoint refusal.
#
# Exit 0 = every check passed, 1 = at least one check failed,
#         2 = tooling failure (nothing was tested).
#
# Overrides: BOX_SLUG (default "local") -> only labels the run in the log
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_ID="BO-LIP-R-U2"
BOX_SLUG="${BOX_SLUG:-local}"

cd "$HERE" || exit 2

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "tooling-failure: python3 not on PATH" >&2
  exit 2
fi

mkdir -p "$HERE/outcomes" || exit 2
LOG="$HERE/outcomes/test-run.log"
: > "$LOG" || exit 2

pass=0
fail=0
failed=""
rows=""

run_one() {
  label="$1"
  shift
  if "$@" >>"$LOG" 2>&1; then
    pass=$((pass + 1))
    rows="$rows
  $label  PASS"
  else
    fail=$((fail + 1))
    failed="$failed $label"
    rows="$rows
  $label  FAIL"
  fi
}

run_one "test_canary_spec.py" "$PY" "$HERE/test_canary_spec.py"
run_one "test_mock_harness.py" "$PY" "$HERE/test_mock_harness.py"
run_one "test_zero_spend.py" "$PY" "$HERE/test_zero_spend.py"
run_one "run_canary.py" "$PY" "$HERE/run_canary.py"

echo "=== v2-13-canary summary (BO-LIP-R-U2) ==="
echo "  check  result$rows"
echo "  pass=$pass fail=$fail spend_usd=0.0 paid_calls=0 mode=mock"
echo "  log: $LOG"

if [ "$fail" -ne 0 ]; then
  echo "V2_13_CANARY_FAIL:$failed"
  exit 1
fi
if [ "$pass" -eq 0 ]; then
  echo "tooling-failure: no checks ran" >&2
  exit 2
fi
echo ALL_V2_13_CANARY_CHECKS_PASS
exit 0
