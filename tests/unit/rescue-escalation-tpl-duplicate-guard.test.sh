#!/usr/bin/env bash
# tests/unit/rescue-escalation-tpl-duplicate-guard.test.sh
# ---------------------------------------------------------------------------
# GAP-DELIVERY-TPL (2026-08-14) -- the escalation template is now shipped in
# TWO places: the repo-root canonical that apply-fleet-standards.sh §5j renders
# (scripts/rescue-escalation-section.md.tpl) and the role-library copy that
# refresh-dept-scripts.py / scaffold_department() mirror onto every
# materialized box
# (23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/
# rescue-escalation-section.md.tpl). Both are rendered by the SAME stamp
# tooling (apply-fleet-standards.sh §5j and stamp-rescue-escalation-section.sh)
# and the repo-root file is the declared SINGLE SOURCE OF TRUTH -- so the two
# copies MUST stay byte-identical. This test proves that on every run, and
# exits 2 (loud) on marker drift the way the sibling
# rescue-escalation-v2-marker-bump.test.sh does.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CANONICAL="$REPO_ROOT/scripts/rescue-escalation-section.md.tpl"
ROLE_LIB="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue-escalation-section.md.tpl"

[ -f "$CANONICAL" ] || { echo "FATAL: $CANONICAL not found"; exit 2; }
[ -f "$ROLE_LIB" ]  || { echo "FATAL: $ROLE_LIB not found (role-library copy missing)"; exit 2; }

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

echo "=== rescue-escalation-tpl-duplicate-guard.test.sh ==="
echo "  canonical: $CANONICAL"
echo "  role-lib:  $ROLE_LIB"

if cmp -s "$CANONICAL" "$ROLE_LIB"; then
  ok "role-library copy is byte-identical to the canonical repo-root template"
else
  bad "role-library copy DIVERGED from the canonical repo-root template"
  echo "  --- sha256 ---"
  shasum -a 256 "$CANONICAL" "$ROLE_LIB" | sed 's/^/    /'
  echo "  --- diff (canonical vs role-library) ---"
  diff -u "$CANONICAL" "$ROLE_LIB" | sed 's/^/    /' | head -60
fi

# The role-library copy must carry the V2 marker pair and the LOOP: line --
# otherwise a box materialized from the role-library learns a stale shape.
if grep -q "RESCUE_ESCALATION_BOXNAME_V2" "$ROLE_LIB"; then
  ok "role-library copy carries the V2 marker pair"
else
  bad "role-library copy is missing the V2 marker"
fi
if grep -q "LOOP:" "$ROLE_LIB"; then
  ok "role-library copy carries the LOOP: routing line"
else
  bad "role-library copy is missing the LOOP: routing line"
fi

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
echo ""
[ "$FAIL" -eq 0 ]
