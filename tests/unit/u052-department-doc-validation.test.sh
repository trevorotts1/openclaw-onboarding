#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/qc-validate-department-docs.py"
DOC="$REPO_ROOT/23-ai-workforce-blueprint/DEPARTMENTS.md"
failures=0

echo "=== U052: Department Documentation Validation ==="

echo "--- Test 1: baseline"
if python3 "$VALIDATOR"; then echo "[PASS] Test 1"
else echo "[FAIL] Test 1"; failures=$((failures + 1)); fi

echo "--- Test 2: mutation proof (RED)"
cp "$DOC" "$DOC.bak"
sed -i '' 's/quality-control/TOTALLY-FAKE-DEPT/g' "$DOC" 2>/dev/null || sed -i 's/quality-control/TOTALLY-FAKE-DEPT/g' "$DOC"
if python3 "$VALIDATOR"; then echo "[FAIL] Test 2: mutation not detected"; failures=$((failures + 1))
else echo "[PASS] Test 2: mutation detected (RED)"; fi
mv "$DOC.bak" "$DOC"

echo "--- Test 3: revert (GREEN)"
if python3 "$VALIDATOR"; then echo "[PASS] Test 3"
else echo "[FAIL] Test 3"; failures=$((failures + 1)); fi

echo "--- Test 4: count"
if grep -q '23 mandatory' "$DOC"; then echo "[PASS] Test 4"
else echo "[FAIL] Test 4"; failures=$((failures + 1)); fi

echo ""
if [ "$failures" -eq 0 ]; then echo "=== U052 VALIDATION: ALL PASSED ==="; exit 0
else echo "=== U052 VALIDATION: $failures FAILURE(S) ==="; exit 1; fi
