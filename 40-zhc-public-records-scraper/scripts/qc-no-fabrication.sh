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

# assert_honest_gap <json> — the resolve() no-fabrication predicate, as ONE
# reusable, independently drivable function (SK1-30 / T0-55).
#
# It used to be `has("resolved")`. A response of
#   {"resolved": true, "county": "...", "state": "..."}
# for a deliberately unresolvable address satisfied that: the gate asserted the
# PRESENCE of the field whose VALUE is the entire finding, so the exact failure
# it was written to catch passed it. The predicate now asserts the VALUE is
# false AND that no county/state was invented alongside it.
#
# Exit 0 = honest gap; 1 = a fabricated resolution. Driven directly by
# tests/unit/records-pipeline-fail-closed.test.sh with a truthy stub, so the
# predicate is observed going RED and not only green.
assert_honest_gap() {
  local json="${1:-}"
  command -v jq >/dev/null 2>&1 || { echo "assert_honest_gap: jq required" >&2; return 2; }
  printf '%s' "$json" | jq -e 'type=="object"' >/dev/null 2>&1 \
    || { echo "assert_honest_gap: not a JSON object: $json" >&2; return 1; }
  printf '%s' "$json" | jq -e 'has("resolved")' >/dev/null 2>&1 \
    || { echo "assert_honest_gap: no explicit resolved field: $json" >&2; return 1; }
  printf '%s' "$json" | jq -e '.resolved == false' >/dev/null 2>&1 \
    || { echo "assert_honest_gap: resolved is not false — the router claimed to resolve an unresolvable query: $json" >&2; return 1; }
  printf '%s' "$json" | jq -e '((.county_fips // "") == "") and ((.state // "") == null or (.state // "") == "") and ((.county_name // "") == null or (.county_name // "") == "")' >/dev/null 2>&1 \
    || { echo "assert_honest_gap: an honest gap carries populated county/state fields (invented location): $json" >&2; return 1; }
  return 0
}

if [ "${1:-}" = "assert_honest_gap" ]; then
  assert_honest_gap "${2:-}"; exit $?
fi

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

  # resolve(garbage) must NOT fabricate coordinates/county — resolved must be
  # FALSE, and no county/state may be invented alongside it (T0-55).
  R="$(bash "$LIB" resolve 'zzzz-no-such-address-zzzz, XX 00000' 2>/dev/null || true)"
  if assert_honest_gap "$R"; then
    echo "  [PASS] resolve(garbage) => resolved:false with no invented county/state ($R)"
  else
    echo "  [FAIL] resolve(garbage) did not return an honest gap: $R"; FAIL=1
  fi

  # SELF-PROOF: the predicate must REJECT a fabricated resolution. A gate that
  # has only ever been observed passing has not been observed at all.
  STUB='{"resolved":true,"source":"census","county_fips":"17167","state":"17","county_name":"Sangamon"}'
  if assert_honest_gap "$STUB" 2>/dev/null; then
    echo "  [FAIL] the no-fabrication predicate ACCEPTED a fabricated resolution — the gate cannot go red"; FAIL=1
  else
    echo "  [PASS] the no-fabrication predicate REJECTS a fabricated resolution (proven red, not only green)"
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
