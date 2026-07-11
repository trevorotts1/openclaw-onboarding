#!/usr/bin/env bash
# =============================================================================
# RESCUE RANGERS :: verify.sh
# The department's failable OFFLINE drill battery. Zero network, zero model,
# zero live-box touch. Runs every self-test for the rescue tooling and exits
# non-zero on the FIRST failure. This is the green gate for the department code.
# -----------------------------------------------------------------------------
#   bash verify.sh
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3)"
NODE="$(command -v node || true)"

pass=0; fail=0
run() {
  local name="$1"; shift
  printf '\n=== %s ===\n' "$name"
  if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); echo "DRILL FAILED: $name" >&2; fi
}

run "rescue_ledger.py --self-test"            "$PY" "$HERE/rescue_ledger.py" --self-test
run "rescue_cc_board.py --self-test"          "$PY" "$HERE/rescue_cc_board.py" --self-test
run "migrate-rescue-staticdata.py --self-test" "$PY" "$HERE/migrate-rescue-staticdata.py" --self-test
run "stamp-rescue-escalation-section.sh --self-test" bash "$HERE/stamp-rescue-escalation-section.sh" --self-test
if [ -n "$NODE" ]; then
  run "relay_brain_validation.js --self-test"  "$NODE" "$HERE/relay_brain_validation.js" --self-test
else
  echo "WARN: node not found — skipping relay_brain_validation.js drill (JS still ships)." >&2
fi

printf '\n=== SUMMARY ===\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ] || exit 1
echo "[rescue-rangers verify] ALL OFFLINE DRILLS PASS"
