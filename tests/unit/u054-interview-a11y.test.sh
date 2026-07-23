#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAGE="$ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/intake-miniapp/pages/index.html"
PASS=0; FAIL=0
ok()  { printf '  [PASS] %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  [FAIL] %s\n' "$1" >&2; FAIL=$((FAIL+1)); }
echo "======= u054-interview-a11y.test.sh ======="
[ -f "$PAGE" ] || { bad "Page missing"; exit 1; }
echo "--- (A) Structural ARIA ---"
grep -q 'role="progressbar"' "$PAGE" && ok "progressbar" || bad "progressbar missing"
grep -q 'aria-valuenow' "$PAGE" && ok "aria-valuenow" || bad "aria-valuenow missing"
grep -q 'role="main"' "$PAGE" && ok "main" || bad "main missing"
grep -q 'role="status"' "$PAGE" && ok "status" || bad "status missing"
grep -q 'role="contentinfo"' "$PAGE" && ok "contentinfo" || bad "contentinfo missing"
echo "--- (B) Radio ---"
[ "$(grep -cE 'role[=:].?"radio"' "$PAGE")" -ge 2 ] && ok "radio>=2" || bad "radio missing"
[ "$(grep -cE 'role[=:].?"radiogroup"' "$PAGE")" -ge 1 ] && ok "radiogroup" || bad "radiogroup missing"
echo "--- (C) Keyshortcuts ---"
[ "$(grep -cE 'aria-keyshortcuts' "$PAGE")" -ge 2 ] && ok "keyshortcuts" || bad "keyshortcuts missing"
echo "--- (D) Alt+N ---"
grep -qE 'altKey.*key.*[nN]' "$PAGE" && ok "Alt+N" || bad "Alt+N missing"
echo "--- (E) Focus ---"
grep -q '\.focus()' "$PAGE" && ok "focus()" || bad "focus() missing"
echo "--- (F) Alert ---"
[ "$(grep -cE 'role[=:].?"alert"' "$PAGE")" -ge 1 ] && ok "alert" || bad "alert missing"
echo "--- (G) aria-live ---"
[ "$(grep -cE 'aria-live' "$PAGE")" -ge 1 ] && ok "aria-live" || bad "aria-live missing"
echo "--- (H) :focus-visible ---"
grep -q ':focus-visible' "$PAGE" && ok "focus-visible" || bad "focus-visible missing"
echo "--- (I) Heading ---"
[ "$(grep -cE 'role[=:].?"heading"' "$PAGE")" -ge 1 ] && ok "heading" || bad "heading missing"
echo "--- (J) .sr-only ---"
grep -q 'sr-only' "$PAGE" && ok "sr-only" || bad "sr-only missing"
echo "=== RESULTS: $PASS pass, $FAIL fail ==="
[ "$FAIL" -gt 0 ] && exit 1
exit 0
