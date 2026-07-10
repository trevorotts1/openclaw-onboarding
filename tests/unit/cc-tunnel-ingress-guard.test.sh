#!/usr/bin/env bash
# tests/unit/cc-tunnel-ingress-guard.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for the "Command Center public link 502s / CF 1303 no-route"
# wrong-port bug (branch fix/cc-tunnel-wrong-port).
#
# ROOT CAUSE guarded here: the fleet runs ONE cloudflared tunnel per box with a
# SINGLE ingress array carrying several hostnames (CC dashboard -> :4000, gateway
# -> :18789, podcast -> :4010). Cloudflare's PUT /configurations REPLACES the
# whole array, so any writer that emits a freshly-built array (a "full-replace")
# instead of GET->merge->PUT deletes the sibling rules — dropping the CC's :4000
# rule (=> CF 1303) or leaving the CC host on the wrong port (=> 502).
#
# This test exercises the SHIPPING helpers (shared-utils/cc-tunnel-ingress.sh)
# and asserts:
#   1. cc_ingress_merge preserves every sibling rule (never a full-replace).
#   2. cc_ingress_assert_cc_port FAILS LOUD on a dropped or wrong-port CC rule.
#   3. the fixed Skill-38 writer no longer emits a bare full-replace ingress.
#   4. the CC port literal is the SAME across the lib and the writers (one source
#      of truth — no silent 4000/3000/4010 drift).
#
# Fully offline/hermetic (jq only). bash 3.2-safe. Exit 0 = pass, 1 = fail.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB="$REPO_ROOT/shared-utils/cc-tunnel-ingress.sh"
S38="$REPO_ROOT/38-conversational-ai-system/scripts/13-create-cloudflare-tunnel.sh"
CREATE_TUNNEL="$REPO_ROOT/32-command-center-setup/scripts/create-tunnel.sh"
RFI="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
eq()   { if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (got '$1' want '$2')"; fi; }

echo "=== cc-tunnel-ingress-guard.test.sh ==="
command -v jq >/dev/null 2>&1 || { echo "  FAIL: jq not on PATH"; exit 1; }
for f in "$LIB" "$S38" "$CREATE_TUNNEL" "$RFI"; do
  [ -f "$f" ] || { echo "  FAIL: required file not found: $f"; exit 1; }
done

# shellcheck source=/dev/null
. "$LIB"

# A realistic SHARED per-box tunnel as CF GET /configurations returns it:
# CC dashboard on :4000 alongside a podcast board on :4010 and a 404 catch-all.
SHARED_CFG='{"success":true,"result":{"source":"cloudflare","config":{"ingress":[
  {"hostname":"acme.zerohumanworkforce.com","service":"http://localhost:4000"},
  {"hostname":"acme-podcast.zerohumanworkforce.com","service":"http://localhost:4010"},
  {"service":"http_status:404"}
]}}}'
CC_HOST="acme.zerohumanworkforce.com"

# ── 1. Authoritative constant is 4000 ───────────────────────────────────────
eq "$CC_INGRESS_PORT"    "4000"                  "CC_INGRESS_PORT authoritative = 4000"
eq "$CC_INGRESS_SERVICE" "http://localhost:4000" "CC_INGRESS_SERVICE = http://localhost:4000"

# ── 2. cc_ingress_merge PRESERVES siblings (adds gateway host, keeps CC + podcast) ─
MERGED="$(cc_ingress_merge "$SHARED_CFG" "acme-hooks.zerohumanworkforce.com" "http://127.0.0.1:18789" "^/hooks/")"
eq "$(cc_ingress_service_for_host "$MERGED" "$CC_HOST")"                        "http://localhost:4000"  "merge preserved CC rule -> :4000"
eq "$(cc_ingress_service_for_host "$MERGED" "acme-podcast.zerohumanworkforce.com")" "http://localhost:4010"  "merge preserved podcast sibling -> :4010"
eq "$(cc_ingress_service_for_host "$MERGED" "acme-hooks.zerohumanworkforce.com")"   "http://127.0.0.1:18789" "merge added gateway host -> :18789"
# exactly one catch-all, and it is last
catch_n="$(cc_ingress_of "$MERGED" | jq '[.[] | select(.hostname|not)] | length')"
last_is_catch="$(cc_ingress_of "$MERGED" | jq -r '.[-1] | (.service=="http_status:404" and (has("hostname")|not))')"
if [ "$catch_n" = "1" ] && [ "$last_is_catch" = "true" ]; then
  pass "merge keeps exactly one catch-all, last"
else
  fail "merge catch-all wrong (count=$catch_n last_is_catch=$last_is_catch)"
fi

# ── 3. Guard PASSES on a healthy CC rule ────────────────────────────────────
if cc_ingress_assert_cc_port "$MERGED" "$CC_HOST" 1 2>/dev/null; then
  pass "guard PASSES when CC host -> :4000 is present"
else
  fail "guard wrongly failed on a healthy CC rule"
fi

# ── 4. Guard FAILS LOUD on a WRONG-PORT CC rule (the 502 signature) ─────────
CLOBBERED='{"config":{"ingress":[
  {"hostname":"acme.zerohumanworkforce.com","service":"http://localhost:18789"},
  {"service":"http_status:404"}]}}'
if cc_ingress_assert_cc_port "$CLOBBERED" "$CC_HOST" 1 2>/dev/null; then
  fail "guard did NOT catch CC host re-pointed to :18789 (would 502)"
else
  pass "guard FAILS LOUD on CC host -> wrong port :18789 (502 signature)"
fi

# ── 5. Guard FAILS LOUD on a DROPPED CC rule (the CF-1303 signature) ────────
# This is exactly what the OLD Skill-38 full-replace produced on a shared tunnel.
FULL_REPLACE='{"config":{"ingress":[
  {"hostname":"acme-hooks.zerohumanworkforce.com","service":"http://127.0.0.1:18789"},
  {"service":"http_status:404"}]}}'
if cc_ingress_assert_cc_port "$FULL_REPLACE" "$CC_HOST" 1 2>/dev/null; then
  fail "guard did NOT catch a dropped CC rule (would be CF 1303 no-route)"
else
  pass "guard FAILS LOUD when the CC rule was dropped (CF-1303 signature)"
fi

# ── 6. The fix actually replaces the OLD full-replace in the Skill-38 writer ──
# It must now GET the current config and MERGE; it must NOT PUT a bare 2-rule
# ingress built from scratch (the clobber). Guard against silent regression.
# shellcheck disable=SC2016  # literal '$host' / '$TUNNEL_ID' are grep patterns, not expansions
if grep -q 'CUR_CFG=' "$S38" \
   && grep -Eq 'map\(select\(has\("hostname"\) and \(\.hostname != \$host\)\)\)' "$S38"; then
  pass "Skill-38 writer does GET->merge (preserves sibling hostname rules)"
else
  fail "Skill-38 writer no longer merges — full-replace clobber may have returned"
fi
# The tell-tale old full-replace was a --data string embedding BOTH the hostname
# and http_status:404 inline. That literal must be gone.
# shellcheck disable=SC2016
if grep -Eq -- '--data "\{\\"config\\":\{\\"ingress\\":\[\{\\"hostname\\".*http_status:404' "$S38"; then
  fail "Skill-38 still contains the inline full-replace ingress --data (the bug)"
else
  pass "Skill-38 no longer contains the inline full-replace ingress --data"
fi
if grep -q 'CC-INGRESS-GUARD FAIL' "$S38"; then
  pass "Skill-38 writer has the fail-loud CC-port guard before PUT"
else
  fail "Skill-38 writer is missing the CC-port guard"
fi

# ── 7. ONE source of truth: the CC port literal matches across lib + writers ──
# run-full-install.sh DASHBOARD_PORT and create-tunnel.sh CC_INGRESS_PORT and the
# Skill-38 guard's CC_PORT_EXPECTED must all equal the lib's CC_INGRESS_PORT.
rfi_port="$(grep -E '^DASHBOARD_PORT=' "$RFI" | head -1 | sed -E 's/.*=([0-9]+).*/\1/')"
ct_port="$(grep -E 'CC_INGRESS_PORT="\$\{CC_INGRESS_PORT:-[0-9]+\}"' "$CREATE_TUNNEL" | head -1 | sed -E 's/.*:-([0-9]+)\}.*/\1/')"
s38_port="$(grep -E 'CC_PORT_EXPECTED="[0-9]+"' "$S38" | head -1 | sed -E 's/.*"([0-9]+)".*/\1/')"
eq "$rfi_port"  "$CC_INGRESS_PORT" "CC port literal in run-full-install == authoritative $CC_INGRESS_PORT"
eq "$ct_port"   "$CC_INGRESS_PORT" "CC port literal in create-tunnel == authoritative $CC_INGRESS_PORT"
eq "$s38_port"  "$CC_INGRESS_PORT" "CC port literal in skill38-guard == authoritative $CC_INGRESS_PORT"

# ── 9. Exercise the SHIPPING Skill-38 inline CC-drift guard jq (not a copy) ───
# Extract the exact jq filter the fixed script runs to detect a Command Center
# host on a non-:4000 port, then drive it with fixtures. This locks two edge
# cases the guard MUST get right: hyphenated slugs are NOT false-flagged, and the
# -hooks/-podcast sibling hosts are NEVER flagged.
GUARD_JQ="$(python3 - "$S38" <<'PY'
import re,sys
s=open(sys.argv[1]).read()
m=re.search(r"jq -r --arg p \"\$CC_PORT_EXPECTED\" '(.*?)'\)\"", s, re.S)
sys.stdout.write(m.group(1) if m else "")
PY
)"
if [ -z "$GUARD_JQ" ]; then
  fail "could not extract the Skill-38 inline guard jq (structure changed?)"
else
  pass "extracted the live Skill-38 inline CC-drift guard jq"
  gdrift() { printf '%s' "$1" | jq -r --arg p "4000" "$GUARD_JQ"; }
  # legit shared tunnel: CC on 4000 + gateway -hooks on 18789 -> no drift
  eq "$(gdrift '{"config":{"ingress":[{"hostname":"acme.zerohumanworkforce.com","service":"http://localhost:4000"},{"hostname":"acme-hooks.zerohumanworkforce.com","service":"http://localhost:18789"},{"service":"http_status:404"}]}}')" \
     "" "shipping guard: legit shared tunnel is NOT flagged"
  # hyphenated slug CC on 4000 -> no false positive
  eq "$(gdrift '{"config":{"ingress":[{"hostname":"star-bobatoon.zerohumanworkforce.com","service":"http://localhost:4000"},{"hostname":"star-bobatoon-hooks.zerohumanworkforce.com","service":"http://localhost:18789"},{"service":"http_status:404"}]}}')" \
     "" "shipping guard: hyphenated CC slug is NOT false-flagged"
  # podcast sibling on 4010 -> not flagged
  eq "$(gdrift '{"config":{"ingress":[{"hostname":"acme.zerohumanworkforce.com","service":"http://localhost:4000"},{"hostname":"acme-podcast.zerohumanworkforce.com","service":"http://localhost:4010"},{"service":"http_status:404"}]}}')" \
     "" "shipping guard: -podcast sibling on :4010 is NOT flagged"
  # pre-broken CC clobbered to 18789 -> flagged (names the host)
  eq "$(gdrift '{"config":{"ingress":[{"hostname":"acme.zerohumanworkforce.com","service":"http://localhost:18789"},{"service":"http_status:404"}]}}')" \
     "acme.zerohumanworkforce.com -> http://localhost:18789" "shipping guard: CC clobbered to :18789 IS flagged"
fi

# ── 8. create-tunnel.sh fails loud (exit 7) on the local-up / public-down case ─
if grep -q 'TUNNEL INGRESS WRONG-PORT / NO-ROUTE' "$CREATE_TUNNEL" \
   && grep -q '502|1033|1303|530|503' "$CREATE_TUNNEL"; then
  pass "create-tunnel.sh diagnoses wrong-port/no-route loudly (not a soft warning)"
else
  fail "create-tunnel.sh missing the loud wrong-port/no-route diagnosis"
fi

echo ""
echo "  RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
