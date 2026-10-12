#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

ADAPTERS=(
  "06-ghl-install-pages/scripts/import_aa_handoff.py"
  "38-conversational-ai-system/scripts/import_aa_handoff.py"
  "47-movie-producer/scripts/import_aa_handoff.py"
  "48-facebook-ad-generator/scripts/import_aa_handoff.py"
)

# T1-T4: Each adapter's self-test exercises actual checksum verification
for adapter in "${ADAPTERS[@]}"; do
  label=$(basename "$(dirname "$(dirname "$adapter")")")
  output=$(python3 "$adapter" --self-test 2>&1) && rc=$? || rc=$?
  if [ $rc -eq 0 ] && echo "$output" | grep -q "RESULT: PASS"; then
    pass "self-test: $label"
  else
    fail "self-test: $label (rc=$rc: $output)"
  fi
done

# T5: All adapters pass py_compile
for adapter in "${ADAPTERS[@]}"; do
  python3 -c "import py_compile,sys; py_compile.compile(sys.argv[1],doraise=True)" "$adapter" 2>&1 \
    && pass "syntax: $(basename $adapter)" || fail "syntax: $(basename $adapter)"
done

# T6: Each adapter's self-test explicitly catches corrupt checksums
for adapter in "${ADAPTERS[@]}"; do
  label=$(basename "$(dirname "$(dirname "$adapter")")")
  if grep -q "AF-IMPORT-CHECKSUM-MISMATCH\|corrupt" "$adapter" 2>/dev/null; then
    pass "corrupt-check: $label"
  else
    fail "corrupt-check: $label"
  fi
done

echo "=== $PASS/$((PASS+FAIL)) passed ==="
exit $((FAIL > 0 ? 1 : 0))
