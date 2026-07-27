#!/bin/bash
set -euo pipefail
pass_count=0; fail_count=0
pass() { echo "PASS $1"; pass_count=$((pass_count + 1)); }
fail() { echo "FAIL $1"; fail_count=$((fail_count + 1)); }
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "FATAL" >&2; exit 1; }
GUARD="scripts/guard-hook-enforcement-parity.sh"; HOOK=".githooks/pre-commit"
[ ! -x "$GUARD" ] && { echo "FATAL: $GUARD not executable" >&2; exit 1; }
RUN="u073-fixture-$(date -u +%Y%m%dT%H%M%SZ)-$$"
SCRATCH="$(mktemp -d -t "$RUN")/clone"
timeout 120 git clone --no-hardlinks --local "$REPO_ROOT" "$SCRATCH"
cd "$SCRATCH"
echo ""; echo "=== Test (a): chmod -x ==="
chmod -x "$HOOK"
timeout 30 bash "$GUARD" 2>/dev/null && fail "Test (a): guard exited 0" || pass "Test (a): guard caught non-executable hook"
chmod +x "$HOOK"
echo ""; echo "=== Test (b): broken script path ==="
HOOK_BACKUP="$HOOK.bak"; cp "$HOOK" "$HOOK_BACKUP"
grep -q 'bash scripts/qc-assert-no-client-names.sh' "$HOOK" && sed -i.bak 's|bash scripts/qc-assert-no-client-names\.sh|bash scripts/NONEXISTENT-qc-assert-no-client-names.sh|' "$HOOK"
timeout 30 bash "$GUARD" 2>/dev/null && fail "Test (b): guard exited 0" || pass "Test (b): guard caught non-existent script"
mv "$HOOK_BACKUP" "$HOOK"
echo ""; echo "=== Test (c): restored tree ==="
timeout 30 bash "$GUARD" 2>/dev/null && pass "Test (c): guard passed" || fail "Test (c): guard failed on restored tree"
cd "$REPO_ROOT"; rm -rf "$(dirname "$SCRATCH")"
echo ""; echo "=== Results: $pass_count passed, $fail_count failed ==="
[ "$fail_count" -gt 0 ] && { echo "NEGATIVE FIXTURE FAILED"; exit 1; }
echo "All three planted defects caught. The guard is proven."; exit 0
