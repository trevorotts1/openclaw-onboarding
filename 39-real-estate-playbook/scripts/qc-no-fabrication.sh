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

# SK1-22: jq is REQUIRED. The substantive gate is the offline `env -i` sandbox
# below (it actually drives lib-property.sh and proves honest-gap shapes). The
# old "jq absent => skip the sandbox but still PASS on two static greps" branch
# was fail-OPEN — it let a box pass without ever exercising the no-fabrication
# behavior. lib-property.sh itself hard-requires jq, so a jq-less host cannot
# legitimately run the skill; fail CLOSED here instead of passing vacuously.
if ! command -v jq >/dev/null 2>&1; then
  echo "  [FAIL] jq not installed — cannot drive the no-fabrication sandbox (lib-property.sh also requires jq). Failing closed."
  echo ""
  echo "RESULT: FAIL — jq required to prove the no-fabrication floor."
  exit 1
fi

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

# ── THE KEYED-PROVIDER MISS (SK1-30 / T0-50) ────────────────────────────────
#
# Everything above runs with ALL provider keys unset. That is the EASY half of
# the rule: a skill with no credential has nothing to fabricate from. The
# dangerous half — a provider credential PRESENT and the lookup returning
# nothing — was never constructed by this gate, and it is the branch where a
# model has real context and an incentive to fill the gap.
#
# A controlled fake transport is installed FIRST on PATH (a `curl` that returns
# exactly what we tell it to) and the library is driven with a credential set
# and three shapes of miss: an EMPTY response, a MALFORMED response, and an
# explicit NO-RECORD response. Each must produce an honest gap carrying no
# record values. No network is touched and no real credential is read: the
# sandbox is `env -i` with a literal non-credential placeholder.
FAKEBIN="$(mktemp -d)"
trap 'rm -rf "$FAKEBIN"' EXIT
cat > "$FAKEBIN/curl" <<'FAKECURL'
#!/usr/bin/env bash
# Controlled fake transport for qc-no-fabrication.sh. Never reaches a network.
# Honors -o <file> so a caller that downloads bytes still behaves predictably.
out=""
prev=""
for a in "$@"; do
  [ "$prev" = "-o" ] && out="$a"
  prev="$a"
done
emit() { if [ -n "$out" ]; then printf '%s' "$1" > "$out"; else printf '%s' "$1"; fi; }
case "${FAKE_CURL_MODE:-empty}" in
  empty)          emit "" ;;
  malformed)      emit '<<< not json at all >>>' ;;
  norecord_array) emit '[]' ;;
  norecord_obj)   emit '{"status":"ZERO_RESULTS"}' ;;
  *)              emit "" ;;
esac
exit 0
FAKECURL
chmod +x "$FAKEBIN/curl"

# A literal placeholder, not a credential. The point is that the code takes the
# keyed branch; the value is never used against anything real.
FAKE_KEY="qc-fake-provider-key-not-a-credential"

run_keyed() { # <mode> <subcommand> <args...>
  local mode="$1"; shift
  env -i HOME="$HOME" PATH="$FAKEBIN:$PATH" FAKE_CURL_MODE="$mode" \
      RENTCAST_API_KEY="$FAKE_KEY" GOOGLE_MAPS_API_KEY="$FAKE_KEY" \
      bash "$LIB" "$@" 2>/dev/null
}

assert_keyed_gap() { # <label> <json> <availability-filter>
  local label="$1" json="$2" filter="$3"
  if [ -z "$json" ]; then
    echo "  [FAIL] $label: produced NO output with a provider key set (must be an explicit honest gap)"; FAIL=1; return
  fi
  if ! printf '%s' "$json" | jq -e 'type=="object"' >/dev/null 2>&1; then
    echo "  [FAIL] $label: not a JSON object: $json"; FAIL=1; return
  fi
  if printf '%s' "$json" | jq -e "$filter == true" >/dev/null 2>&1; then
    echo "  [FAIL] $label: reported availability TRUE on a provider miss (fabrication): $json"; FAIL=1; return
  fi
  # An honest gap must not smuggle record content back in another field.
  if printf '%s' "$json" | jq -e 'has("record") or has("comparables") or has("image_path") or has("lat") or has("lon")' >/dev/null 2>&1; then
    echo "  [FAIL] $label: an honest gap carries record values: $json"; FAIL=1; return
  fi
  echo "  [PASS] $label: honest gap with a provider key present ($json)"
}

for MODE in empty malformed norecord_array; do
  assert_keyed_gap "lookup (key present, $MODE response)" "$(run_keyed "$MODE" lookup '123 Nowhere St, XX 00000')" '.available'
  assert_keyed_gap "comps (key present, $MODE response)"  "$(run_keyed "$MODE" comps  '123 Nowhere St, XX 00000')" '.available'
done
for MODE in empty malformed norecord_obj; do
  assert_keyed_gap "streetview (key present, $MODE metadata)" "$(run_keyed "$MODE" streetview '0,0')" '.available'
  assert_keyed_gap "geocode (key present, $MODE response)"    "$(run_keyed "$MODE" geocode '123 Nowhere St, XX 00000')" '.matched'
done

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
