#!/usr/bin/env bash
# qc-compliance.sh — machine-enforce the Skill 40 COMPLIANCE posture with
# BEHAVIORAL assertions (drive lib-records.sh against a MOCK target), not comment
# greps. It proves the router actually ENFORCES, not merely documents:
#   1. robots.txt Disallow is honored (incl. the `*` wildcard) — a disallowed
#      path is BLOCKED (and query() emits compliance_block/robots_disallow).
#   2. A ToS reference must be a REAL url — a placeholder tos_url is rejected, and
#      a config carrying a placeholder tos_url / validated:false is NOT servable.
#   3. A persisted per-target ToS acknowledgement is required before a live fetch.
#   4. Attribution is required — cache_put REFUSES a record missing
#      source + retrieved_at (an unattributed result is not a record).
#
# Everything runs OFFLINE against a sandbox MASTER_FILES_DIR + mock configs.
# Exit 0 = posture holds; 1 = a violation. BASH (jq core).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib-records.sh"
FAIL=0

echo "=== qc-compliance (Skill 40): behavioral robots + ToS + attribution ==="

# SK1-30 / T0-54: jq is REQUIRED. This branch used to print
#   RESULT: PASS (skipped — jq unavailable)
# and exit 0 having evaluated NOTHING — on any box without jq, the compliance
# gate for a public-records scraper emitted the literal string PASS. INSTALL.md
# names this script as one of three that must PASS before the skill counts as
# installed, so a missing utility certified the whole compliance posture.
# A gate that cannot run reports that it cannot run; it never counts as a pass.
# (The sibling gate in Skill 39 already handled this correctly by exiting 1.)
if ! command -v jq >/dev/null 2>&1; then
  echo "  [FAIL] jq not present — every assertion in this gate needs jq, and lib-records.sh itself hard-requires jq."
  echo ""
  echo "RESULT: FAIL (INCOMPLETE — jq unavailable, no compliance assertion could be evaluated). Install jq and re-run."
  exit 1
fi
[ -f "$LIB" ] || { echo "  [FAIL] lib-records.sh not found at $LIB"; exit 1; }

SANDBOX="$(mktemp -d)"
export MASTER_FILES_DIR="$SANDBOX"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

# ── 1. robots Disallow is honored, wildcard-safe ──────────────────────────────
# A disallowed path must BLOCK. This is the decision that makes query() emit
# compliance_block/robots_disallow.
bash "$LIB" robots_match "/records/search" "/"  && pass "robots 'Disallow: /' blocks every path" \
  || fail "robots 'Disallow: /' did not block"
bash "$LIB" robots_match "/records/search" "/*" && pass "robots 'Disallow: /*' blocks (wildcard parsed, not literal)" \
  || fail "robots 'Disallow: /*' did not block — wildcard parsed literally (the old bug)"
bash "$LIB" robots_match "/records/search" "/private*" \
  && fail "'Disallow: /private*' wrongly blocked an unrelated path" \
  || pass "'Disallow: /private*' does NOT block an unrelated path"
bash "$LIB" robots_match "/private/x" "/private*" && pass "'Disallow: /private*' blocks its own subtree" \
  || fail "'Disallow: /private*' failed to block its subtree"
bash "$LIB" robots_match "/a/b" "/a/*/c" && pass "embedded/unevaluable wildcard FAILS CLOSED (blocked)" \
  || fail "embedded wildcard did not fail closed"

# Static backstop: query() actually WIRES the compliance_block emit on the robots
# and ToS paths (so the behavioral robots decision above has an enforcement site).
grep -q 'compliance_block' "$LIB" && grep -q 'robots_disallow' "$LIB" && grep -q 'tos_unacknowledged' "$LIB" \
  && pass "query() emits compliance_block for robots_disallow + tos_unacknowledged" \
  || fail "query() does not wire compliance_block for robots/ToS"

# ── 2. placeholder tos_url is rejected ────────────────────────────────────────
bash "$LIB" tos_valid "https://county.example/terms" && pass "a real https tos_url is accepted" \
  || fail "a real tos_url was rejected"
bash "$LIB" tos_valid "<OPERATOR_FILLS_TOS_URL>" && fail "placeholder tos_url was ACCEPTED" \
  || pass "placeholder tos_url '<OPERATOR_FILLS_TOS_URL>' is rejected"
bash "$LIB" tos_valid "" && fail "empty tos_url was ACCEPTED" || pass "empty tos_url is rejected"

# A config with a placeholder tos_url (or validated:false) is NOT tier-servable.
MOCK="$SANDBOX/mock-target.json"
cat > "$MOCK" <<'J'
{"slug":"mock-target","county_fips":"99999","validated":true,"portal_url":"https://county.example","tos_url":"<OPERATOR_FILLS_TOS_URL>"}
J
bash "$LIB" config_servable "$MOCK" && fail "mock config with a placeholder tos_url was treated as servable" \
  || pass "mock config with a placeholder tos_url is NOT servable (falls through to validate)"
cat > "$MOCK" <<'J'
{"slug":"mock-target","county_fips":"99999","validated":false,"portal_url":"https://county.example","tos_url":"https://county.example/terms"}
J
bash "$LIB" config_servable "$MOCK" && fail "mock config validated:false was treated as servable" \
  || pass "mock config validated:false is NOT servable (forces 05-validate-target.sh)"
cat > "$MOCK" <<'J'
{"slug":"mock-target","county_fips":"99999","validated":true,"portal_url":"https://county.example","tos_url":"https://county.example/terms"}
J
bash "$LIB" config_servable "$MOCK" && pass "a fully validated, non-placeholder config IS servable" \
  || fail "a fully validated config was wrongly rejected"

# ── 3. persisted per-target ToS acknowledgement is required ───────────────────
bash "$LIB" tos_ack mock-target && fail "ToS ack reported present before any ack was recorded" \
  || pass "no ToS ack present initially (target would compliance_block/tos_unacknowledged)"
bash "$LIB" ack_tos mock-target "<OPERATOR_FILLS_TOS_URL>" >/dev/null 2>&1 \
  && fail "ack_tos recorded an ack for a PLACEHOLDER tos_url" \
  || pass "ack_tos refuses a placeholder tos_url"
bash "$LIB" ack_tos mock-target "https://county.example/terms" >/dev/null 2>&1 \
  && bash "$LIB" tos_ack mock-target && pass "ack_tos persists a real ack; tos_ack then detects it" \
  || fail "ToS ack persist/detect flow failed"

# ── 4. attribution required — refuse a record missing source/retrieved_at ─────
if bash "$LIB" cache_put mock-target 99999 ownership '{"owner":"REDACTED"}' '123 mock st' >/dev/null 2>&1; then
  fail "cache_put ACCEPTED a record with no source/retrieved_at (unattributed)"
else
  pass "cache_put REFUSES a record missing source + retrieved_at"
fi
if bash "$LIB" cache_put mock-target 99999 ownership \
     '{"owner":"REDACTED","source":"county recorder portal","retrieved_at":"2026-07-05T00:00:00Z"}' '123 mock st' >/dev/null 2>&1; then
  pass "cache_put accepts a properly attributed record"
else
  fail "cache_put rejected a properly attributed record"
fi

# ── 5. cache identity carries the QUERY (SK1-30 / T1-05) ─────────────────────
# Two different addresses in the SAME county for the SAME record type must not
# share a cache entry. Before the fix the key was target|fips|rtype only, so the
# second address was served the first address's attributed record as a cache hit.
K_A="$(bash "$LIB" cache_key mock-target 99999 ownership '123 Main St, Springfield IL')"
K_B="$(bash "$LIB" cache_key mock-target 99999 ownership '987 Other Ave, Springfield IL')"
K_A2="$(bash "$LIB" cache_key mock-target 99999 ownership '123  MAIN ST,  Springfield  IL')"
if [ -n "$K_A" ] && [ "$K_A" != "$K_B" ]; then
  pass "cache key differs for two different queries in the same county/record type"
else
  fail "cache key COLLIDES across two different queries (one property's record would be served under another's address)"
fi
if [ -n "$K_A" ] && [ "$K_A" = "$K_A2" ]; then
  pass "cache key is stable across case/whitespace variants of the SAME query"
else
  fail "cache key is unstable for the same query (every lookup would miss)"
fi
# A record cached under one query must not be reachable under another.
if bash "$LIB" cache_put mock-target 99999 ownership \
     '{"owner":"REDACTED","source":"county recorder portal","retrieved_at":"2026-07-05T00:00:00Z"}' \
     '123 Main St, Springfield IL' >/dev/null 2>&1; then
  if [ -f "$SANDBOX/public-records-cache/v2-$K_A.json" ] && [ ! -f "$SANDBOX/public-records-cache/v2-$K_B.json" ]; then
    pass "the cached record is reachable ONLY under the query it was written for"
  else
    fail "cache entry placement does not follow the query-bound key"
  fi
else
  fail "cache_put refused an attributed record with a query"
fi
# The write refuses to run at all without a query — an unqualified entry can
# never be created by a caller that forgot the new argument.
if bash "$LIB" cache_put mock-target 99999 ownership \
     '{"owner":"REDACTED","source":"county recorder portal","retrieved_at":"2026-07-05T00:00:00Z"}' >/dev/null 2>&1; then
  fail "cache_put ACCEPTED a write with no query (an unqualified, collidable entry)"
else
  pass "cache_put REFUSES a write with no query (query is part of the cache identity)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — compliance posture ENFORCED (robots honored, real ToS + persisted ack required, attribution required, cache identity query-bound)."
  exit 0
else
  echo "RESULT: FAIL — a compliance violation was detected above."
  exit 1
fi
