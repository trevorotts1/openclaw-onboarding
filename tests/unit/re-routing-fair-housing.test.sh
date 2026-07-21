#!/usr/bin/env bash
# tests/unit/re-routing-fair-housing.test.sh
#
# Acceptance tests for T0-52 and T0-50 (SK1-30, Skill 39).
#
#   T0-52  Fair housing was enforced only at the point an event is WRITTEN —
#          after the routing decision had already been made — and qc-fair-housing.sh
#          certified "fair-housing is machine-enforced" from a `grep -qi "never
#          route on"` over a markdown file and two greps over a shell file.
#          The routing decision itself was never examined by anything.
#          scripts/route-lead.sh is now the entry point: it runs the
#          protected-attribute detector over the lead AND the roster BEFORE any
#          filtering or scoring and refuses non-zero.
#
#   T0-50  qc-no-fabrication.sh only ever ran the KEYLESS branch. The dangerous
#          branch — a provider credential PRESENT and the lookup returning
#          nothing — was never constructed. It now is, with a controlled fake
#          transport and three shapes of miss.
#
# MUTATION PROOF: a private copy of route-lead.sh with the detector MOVED BELOW
# the scoring block. The refusal still happens (the exit code alone cannot tell
# the difference) but the scoring trace is no longer empty — so the assertion
# that the refusal precedes scoring turns red, exactly as it must.
#
# Hermetic: private sandbox, synthetic roster and leads, no network, no real box.
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
S39="$REPO_ROOT/39-real-estate-playbook"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== re-routing-fair-housing.test.sh ==="
echo ""

command -v jq >/dev/null 2>&1 || { echo "SKIP-IMPOSSIBLE: jq is required to run this suite"; exit 1; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

COPY="$SANDBOX/repo"; mkdir -p "$COPY"
cp -R "$S39" "$COPY/"
C39="$COPY/$(basename "$S39")"
ENTRY="$C39/scripts/route-lead.sh"
MFD="$SANDBOX/mfd"; mkdir -p "$MFD"

cat > "$SANDBOX/roster.json" <<'ROSTER'
{"version":"1.0.0","agents":[
 {"agent_ref":"T-A1","active":true,"specialties":["buyer","first_time"],"areas":["north"],"capacity_weight":1.0},
 {"agent_ref":"T-A2","active":true,"specialties":["listing","luxury"],"areas":["north"],"capacity_weight":1.0},
 {"agent_ref":"T-A3","active":false,"specialties":["listing","luxury"],"areas":["north"],"capacity_weight":9.0}],
 "fallback_queue":"T-FALLBACK"}
ROSTER
printf '%s' '{"role":"buyer","race":"withheld","area":"north"}'          > "$SANDBOX/lead-race.json"
printf '%s' '{"role":"buyer","familial_status":"withheld","area":"north"}' > "$SANDBOX/lead-familial.json"
printf '%s' '{"role":"seller","signals":["luxury"],"area":"north"}'      > "$SANDBOX/lead-clean.json"
printf '%s' '{"role":"buyer","signals":["first_time"],"area":"north"}'   > "$SANDBOX/lead-buyer.json"
jq '.agents[0] += {"national_origin":"withheld"}' "$SANDBOX/roster.json" > "$SANDBOX/roster-protected.json"
jq '.agents = [{"agent_ref":"<AGENT_REF_1>","active":true,"specialties":["buyer"],"areas":["north"],"capacity_weight":1.0}]' \
   "$SANDBOX/roster.json" > "$SANDBOX/roster-template.json"

# ---------------------------------------------------------------------------
echo "--- T0-52: the entry point exists and is the documented path ---"
[ -f "$ENTRY" ] && pass "T0-52: scripts/route-lead.sh exists" || { fail "T0-52: no routing entry point"; echo "=== Results: $PASS passed, $((FAIL)) failed ==="; exit 1; }
grep -q "route-lead.sh" "$C39/protocols/lead-routing-protocol.md" \
  && pass "T0-52: the lead-routing protocol names the entry point" \
  || fail "T0-52: the protocol does not name the entry point"

echo ""
echo "--- T0-52: a protected attribute is refused BEFORE any scoring ---"
for L in race familial; do
  TR="$SANDBOX/trace-$L.txt"
  OUT="$(MASTER_FILES_DIR="$MFD" SKILL39_ROUTE_TRACE="$TR" HOME="$SANDBOX" \
          bash "$ENTRY" --lead "$SANDBOX/lead-$L.json" --roster "$SANDBOX/roster.json" --json 2>/dev/null)"
  rc=$?
  [ "$rc" -eq 3 ] && pass "T0-52: lead carrying '$L' is REFUSED (exit 3)" \
    || fail "T0-52: lead carrying '$L' was not refused (exit $rc, out=$OUT)"
  [ -z "$OUT" ] && pass "T0-52: no routing decision was emitted for the '$L' lead" \
    || fail "T0-52: a routing decision was emitted for the '$L' lead: $OUT"
  [ ! -s "$TR" ] && pass "T0-52: nothing was filtered or scored before the '$L' refusal (trace empty)" \
    || { fail "T0-52: scoring ran before the '$L' refusal"; sed 's/^/        /' "$TR"; }
done

echo ""
echo "--- T0-52: a protected attribute in the ROSTER is refused too ---"
OUT_R="$(MASTER_FILES_DIR="$MFD" HOME="$SANDBOX" bash "$ENTRY" \
          --lead "$SANDBOX/lead-clean.json" --roster "$SANDBOX/roster-protected.json" --json 2>/dev/null)"
[ $? -eq 3 ] && pass "T0-52: a roster carrying a protected-class field is REFUSED" \
  || fail "T0-52: a protected-class field in the roster did not stop routing (out=$OUT_R)"

echo ""
echo "--- T0-52: the refusal is auditable, and carries key NAMES only ---"
if jq -e -s 'map(select(.event=="lead_route_refused")) | (length > 0) and (.[0].offending_key_names | index("race") != null)' < "$MFD/real-estate-events.jsonl" >/dev/null 2>&1; then
  pass "T0-52: a lead_route_refused event names the offending key"
else
  fail "T0-52: no lead_route_refused event was recorded"
fi
if jq -e -s 'map(select(.event=="lead_route_refused")) | any(.[]; has("race"))' < "$MFD/real-estate-events.jsonl" >/dev/null 2>&1; then
  fail "T0-52: the refusal event itself carries a protected-class FIELD"
else
  pass "T0-52: the refusal event carries no protected-class field of its own"
fi

echo ""
echo "--- T0-52: clean leads still route (anti-false-positive) ---"
TRC="$SANDBOX/trace-clean.txt"
OUT_C="$(MASTER_FILES_DIR="$MFD" SKILL39_ROUTE_TRACE="$TRC" HOME="$SANDBOX" \
          bash "$ENTRY" --lead "$SANDBOX/lead-clean.json" --roster "$SANDBOX/roster.json" --json 2>/dev/null)"
rc_c=$?
if [ "$rc_c" -eq 0 ] && printf '%s' "$OUT_C" | jq -e '.routed == true and .agent_ref == "T-A2"' >/dev/null 2>&1; then
  pass "T0-52: a seller/luxury lead routes to the listing+luxury agent ($OUT_C)"
else
  fail "T0-52: the clean seller lead did not route as expected (exit $rc_c, out=$OUT_C)"
fi
OUT_B="$(MASTER_FILES_DIR="$MFD" HOME="$SANDBOX" bash "$ENTRY" \
          --lead "$SANDBOX/lead-buyer.json" --roster "$SANDBOX/roster.json" --json 2>/dev/null)"
printf '%s' "$OUT_B" | jq -e '.agent_ref == "T-A1"' >/dev/null 2>&1 \
  && pass "T0-52: a first-time buyer lead routes to the buyer+first_time agent" \
  || fail "T0-52: the buyer lead routed wrongly: $OUT_B"
[ -s "$TRC" ] && pass "T0-52: a clean lead DOES reach scoring (the empty-trace assertion is not vacuous)" \
  || fail "T0-52: a clean lead never reached scoring — the trace proves nothing"

echo ""
echo "--- T0-52: an inactive agent is never routed to, and an unfilled roster HOLDS ---"
printf '%s' "$OUT_C" | jq -e '.agent_ref != "T-A3"' >/dev/null 2>&1 \
  && pass "T0-52: the inactive high-capacity agent was not selected" \
  || fail "T0-52: an inactive agent was routed to"
MASTER_FILES_DIR="$MFD" HOME="$SANDBOX" bash "$ENTRY" \
  --lead "$SANDBOX/lead-buyer.json" --roster "$SANDBOX/roster-template.json" --json >/dev/null 2>&1
[ $? -eq 4 ] && pass "T0-52: an unfilled (placeholder) roster HOLDS the lead (exit 4)" \
  || fail "T0-52: a template roster was routed against"

echo ""
echo "--- T0-52 MUTATION: move the detector BELOW the scoring block ---"
MUT="$SANDBOX/route-lead.MUTATED.sh"
cp "$ENTRY" "$MUT"
python3 - "$MUT" <<'MUTMOVE'
import sys
p = sys.argv[1]
s = open(p).read()
d_start = s.index("# ─── STEP 1 (FIRST, ALWAYS)")
d_end = s.index("# ─── STEP 2:")
detector = s[d_start:d_end]
s = s[:d_start] + s[d_end:]
anchor = s.index('_trace "decision:')
insert_at = s.index("\n", anchor) + 1
s = s[:insert_at] + "\n" + detector + s[insert_at:]
open(p, "w").write(s)
MUTMOVE
TRM="$SANDBOX/trace-mutated.txt"
mkdir -p "$SANDBOX/mfd-mut"
MASTER_FILES_DIR="$SANDBOX/mfd-mut" SKILL39_ROUTE_TRACE="$TRM" HOME="$SANDBOX" \
  bash "$MUT" --lead "$SANDBOX/lead-race.json" --roster "$SANDBOX/roster.json" --json >/dev/null 2>&1
rc_m=$?
if [ -s "$TRM" ]; then
  pass "T0-52 MUTATION: with the detector moved below scoring the trace is NON-empty (exit $rc_m) — the before-scoring assertion is discriminating"
else
  fail "T0-52 MUTATION: the trace was still empty with the detector moved — the assertion proves nothing"
fi

echo ""
echo "--- T0-50: the no-fabrication gate exercises the KEYED provider miss ---"
GATE_OUT="$(bash "$C39/scripts/qc-no-fabrication.sh" 2>&1)"
rc_g=$?
[ "$rc_g" -eq 0 ] && pass "T0-50: the Skill 39 no-fabrication gate passes on a healthy tree" \
  || { fail "T0-50: the gate failed"; printf '%s\n' "$GATE_OUT" | sed 's/^/      /'; }
for BRANCH in "key present, empty response" "key present, malformed response" "key present, norecord_array response"; do
  printf '%s' "$GATE_OUT" | grep -q "lookup ($BRANCH)" \
    && pass "T0-50: the gate drives lookup with a $BRANCH" \
    || fail "T0-50: the gate never drove lookup with a $BRANCH"
done
printf '%s' "$GATE_OUT" | grep -q "streetview (key present" \
  && pass "T0-50: the gate drives the image-metadata path with a credential present" \
  || fail "T0-50: the keyed streetview branch is still never exercised"

echo ""
echo "--- T0-50 MUTATION: make the keyed miss fabricate, and require the gate to go red ---"
MUTLIB="$SANDBOX/lib-property.MUTATED.sh"
cp "$C39/scripts/lib-property.sh" "$MUTLIB"
python3 - "$MUTLIB" <<'MUTFAB'
import sys
p = sys.argv[1]
s = open(p).read()
# The keyed-miss branch invents a record instead of returning an honest gap.
old = """    echo '{"available":false,"source":"rentcast","reason":"provider returned no record for this address"}'"""
new = """    echo '{"available":true,"source":"rentcast","record":{"bedrooms":3,"bathrooms":2}}'"""
assert s.count(old) == 1
open(p, "w").write(s.replace(old, new))
MUTFAB
cp "$MUTLIB" "$C39/scripts/lib-property.sh"
bash "$C39/scripts/qc-no-fabrication.sh" >/dev/null 2>&1 \
  && fail "T0-50 MUTATION: the gate PASSED a library that fabricates on a keyed miss — it is not discriminating" \
  || pass "T0-50 MUTATION: the gate goes RED when the keyed-miss branch fabricates a record"

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all fair-housing routing + keyed-provider-miss checks pass"
exit 0
