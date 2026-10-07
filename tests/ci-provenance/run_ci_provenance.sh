#!/usr/bin/env bash
# W4-05-U1 driver: CI + provenance + secret closure.
#
# Runs the three checkers in order and prints one combined table.
# Exit 0 = all three PASS, 1 = at least one FAIL, 2 = tooling failure
# (a checker could not run — never reported as a clean pass).
#
# Stdlib python3 + gh (checker 1 only) + git. No network calls except
# checker 1's GitHub reads. No secrets printed anywhere.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2

declare -a NAMES=()
declare -a CODES=()

run_one() {
  local name="$1"
  shift
  echo "=== $name ==="
  python3 "$@"
  local rc=$?
  echo "--- $name exit=$rc ---"
  NAMES+=("$name")
  CODES+=("$rc")
}

run_one "ci-matrix"            ci_matrix.py
run_one "provenance-closure"   provenance_closure.py
run_one "secret-scan"          secret_scan.py

echo
echo "================ ci-provenance summary ================"
fail=0
tooling=0
for i in "${!NAMES[@]}"; do
  code="${CODES[$i]}"
  case "$code" in
    0) status="PASS" ;;
    2) status="TOOLING"; tooling=1; fail=1 ;;
    *) status="FAIL"; fail=1 ;;
  esac
  printf '%-22s %s (rc=%s)\n' "${NAMES[$i]}" "$status" "$code"
done
echo "receipts:"
ls -1 "$HERE/receipts" 2>/dev/null | sed 's/^/  receipts\//' \
  || echo "  (none)"
echo "======================================================="

if [ "$tooling" -eq 1 ]; then exit 2; fi
if [ "$fail" -eq 1 ]; then exit 1; fi
exit 0