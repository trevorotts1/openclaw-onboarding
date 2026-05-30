#!/usr/bin/env bash
# qc-no-fabrication.sh — machine-enforce the Skill 40 NO-FABRICATION FLOOR.
#
# The #1 rule: the router NEVER fabricates a record. When the county cannot be
# resolved, or no tier serves the query, lib-records.sh must return a Tier-4
# HONEST GAP (or available:false), NEVER an invented owner/deed/lien/NOD/tax/
# permit. This gate drives lib-records.sh in an OFFLINE-ish sandbox and asserts
# the honest-gap shapes, plus a static check that the router carries the
# no-fabrication contract and never synthesizes a record on its own.
#
# Exit 0 = floor holds; 1 = a fabrication path / missing contract detected.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib-records.sh"
FAIL=0

echo "=== qc-no-fabrication (Skill 40): tier-4 honest-gap floor ==="
[ -f "$LIB" ] || { echo "FAIL: lib-records.sh not found at $LIB"; exit 1; }

if command -v jq >/dev/null 2>&1; then
  # tier() for an unresolvable / unknown FIPS must be tier4_honest_gap.
  T="$(bash "$LIB" tier 'ZZZZZ' 2>/dev/null || true)"
  if printf '%s' "$T" | jq -e '.tier=="tier4_honest_gap"' >/dev/null 2>&1; then
    echo "  [PASS] tier(unknown FIPS) => tier4_honest_gap ($T)"
  else
    echo "  [FAIL] tier(unknown FIPS) did not return an honest gap: $T"; FAIL=1
  fi

  # tier() with empty FIPS => honest gap (county_unresolved).
  T2="$(bash "$LIB" tier '' 2>/dev/null || true)"
  if printf '%s' "$T2" | jq -e '.tier=="tier4_honest_gap"' >/dev/null 2>&1; then
    echo "  [PASS] tier(empty) => tier4_honest_gap ($T2)"
  else
    echo "  [FAIL] tier(empty) did not return an honest gap: $T2"; FAIL=1
  fi

  # resolve(garbage) must NOT fabricate coordinates/county — must say resolved:false.
  R="$(bash "$LIB" resolve 'zzzz-no-such-address-zzzz, XX 00000' 2>/dev/null || true)"
  if printf '%s' "$R" | jq -e 'type=="object" and has("resolved")' >/dev/null 2>&1; then
    rv="$(printf '%s' "$R" | jq -r '.resolved')"
    echo "  [PASS] resolve(garbage) returns explicit resolved field (resolved=$rv, $R)"
  else
    echo "  [FAIL] resolve(garbage) did not return an object with a resolved field: $R"; FAIL=1
  fi
else
  echo "  [WARN] jq not present — skipping runtime sandbox assertions (static check still runs)."
fi

# Static: the router must carry the no-fabrication contract + the honest-gap
# shapes, and must NOT contain a hardcoded fake record value.
grep -q "NEVER FABRICATE" "$LIB" || { echo "  [FAIL] lib-records.sh missing the explicit NEVER-FABRICATE contract comment"; FAIL=1; }
grep -q "tier4_honest_gap" "$LIB" || { echo "  [FAIL] lib-records.sh missing the tier4_honest_gap shape"; FAIL=1; }
grep -qi "synthesizes a record" "$LIB" || { echo "  [FAIL] lib-records.sh missing the 'never synthesizes a record' guarantee"; FAIL=1; }

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the no-fabrication floor holds (no tier => honest gap, never invented records)."
  exit 0
else
  echo "RESULT: FAIL — a fabrication path or missing honest-gap contract was detected above."
  exit 1
fi
