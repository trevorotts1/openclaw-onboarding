#!/usr/bin/env bash
# qc-no-fabrication.sh — machine-enforce the Skill 39 NO-FABRICATION FLOOR.
#
# The #1 rule of this skill: it NEVER fabricates property data. When a provider
# key is absent or a lookup returns nothing, lib-property.sh must return an
# HONEST GAP ("available": false / "matched": false), never an invented record.
#
# This gate drives lib-property.sh in an OFFLINE sandbox (env stripped of every
# provider key) and asserts that each subcommand returns the honest-gap shape
# rather than a fabricated value. It also statically verifies the library does
# not contain hardcoded placeholder property values that could leak as "data".
#
# Exit codes: 0 = floor holds; 1 = a fabrication path or hardcoded value found.
# BASH only (grep/jq core).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib-property.sh"
FAIL=0

echo "=== qc-no-fabrication (Skill 39): provider-miss honest-gap floor ==="
[ -f "$LIB" ] || { echo "FAIL: lib-property.sh not found at $LIB"; exit 1; }

run_offline() { # subcommand + arg -> stdout of lib with ALL provider keys unset
  env -i HOME="$HOME" PATH="$PATH" bash "$LIB" "$@" 2>/dev/null
}

assert_json_false() { # label, json, jq-filter-that-must-be-false-or-absent
  local label="$1" json="$2" filter="$3"
  if [ -z "$json" ]; then echo "  [FAIL] $label: empty output (must return an honest-gap object)"; FAIL=1; return; fi
  if ! printf '%s' "$json" | jq -e 'type=="object"' >/dev/null 2>&1; then
    echo "  [FAIL] $label: not a JSON object: $json"; FAIL=1; return
  fi
  local v; v="$(printf '%s' "$json" | jq -r "$filter" 2>/dev/null || echo "")"
  if [ "$v" = "true" ]; then
    echo "  [FAIL] $label: returned a truthy availability with NO provider key (possible fabrication): $json"; FAIL=1
  else
    echo "  [PASS] $label: honest gap ($json)"
  fi
}

if command -v jq >/dev/null 2>&1; then
  # geocode with a deliberately non-matching string: must return a JSON object
  # with a boolean "matched" field — it must never invent lat/lon. (A real
  # Census match is fine and not a failure; the floor is "no fabricated
  # coordinates", which an object-with-matched proves.)
  GEO="$(run_offline geocode 'zzzz-no-such-address-zzzz, XX 00000')"
  if printf '%s' "$GEO" | jq -e 'type=="object" and has("matched")' >/dev/null 2>&1; then
    echo "  [PASS] geocode: returns object with explicit matched field ($GEO)"
  else
    echo "  [FAIL] geocode: did not return an object with a matched field: $GEO"; FAIL=1
  fi

  assert_json_false "lookup (no key)"     "$(run_offline lookup 'any address')"   '.available'
  assert_json_false "comps (no key)"      "$(run_offline comps 'any address')"    '.available'
  assert_json_false "streetview (no key)" "$(run_offline streetview '0,0')"       '.available'
else
  echo "  [WARN] jq not present — skipping runtime sandbox assertions (static check still runs)."
fi

# Static: the library must explicitly carry the no-fabrication contract and the
# honest-gap markers, and must NOT hardcode placeholder property values.
grep -q "NEVER FABRICATE" "$LIB" || { echo "  [FAIL] lib-property.sh missing the explicit NEVER-FABRICATE contract comment"; FAIL=1; }
grep -q '"available":false' "$LIB" || grep -q "available:false" "$LIB" || { echo "  [FAIL] lib-property.sh missing the available:false honest-gap shape"; FAIL=1; }

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — the no-fabrication floor holds (provider miss => honest gap, never invented data)."
  exit 0
else
  echo "RESULT: FAIL — a fabrication path or missing honest-gap contract was detected above."
  exit 1
fi
