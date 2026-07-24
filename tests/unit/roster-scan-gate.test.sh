#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0
ok() { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "=== U116 ==="
S39="$REPO_ROOT/39-real-estate-playbook/scripts/qc-no-personal-data.sh"
S40="$REPO_ROOT/40-zhc-public-records-scraper/scripts/qc-no-personal-data.sh"
for f in "$S39" "$S40"; do
  r="$(echo "$f" | grep -oE '[0-9]+-[^/]+/scripts/qc-no-personal-data.sh')"
  [[ -f "$f" ]] && ok "$r exists" || { bad "$r missing"; continue; }
  grep -q 'ROSTER_LOADED=0' "$f" && ok "$r ROSTER_LOADED init" || bad "$r no ROSTER_LOADED init"
  grep -q 'ROSTER_LOADED=1' "$f" && ok "$r ROSTER_LOADED=1" || bad "$r no ROSTER_LOADED=1"
  grep -q 'ROSTER_LOADED.*-eq 0' "$f" && ok "$r ROSTER_LOADED guard" || bad "$r no ROSTER_LOADED guard"
done
R39="$(timeout 10 bash "$S39" 2>&1; echo "EX=$?")"
echo "$R39" | grep -q 'FAIL.*roster' && ok "s39 fails on absent roster" || bad "s39 no fail: $R39"
echo "$R39" | grep -q 'EX=1' && ok "s39 exits 1" || bad "s39 exit: $R39"
R40="$(timeout 10 bash "$S40" 2>&1; echo "EX=$?")"
echo "$R40" | grep -q 'FAIL.*roster' && ok "s40 fails on absent roster" || bad "s40 no fail: $R40"
echo "$R40" | grep -q 'EX=1' && ok "s40 exits 1" || bad "s40 exit: $R40"
mkdir -p "$TMP/.openclaw"; echo "TestClient" > "$TMP/.openclaw/client-roster.txt"
S39R="$(HOME="$TMP" timeout 10 bash "$S39" 2>&1; echo "EX=$?")"
echo "$S39R" | grep -qv 'FAIL.*roster' && ok "s39 passes with roster" || bad "s39 fails with roster: $S39R"
S40R="$(HOME="$TMP" timeout 10 bash "$S40" 2>&1; echo "EX=$?")"
echo "$S40R" | grep -qv 'FAIL.*roster' && ok "s40 passes with roster" || bad "s40 fails with roster: $S40R"
echo "=== $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] || exit 1
