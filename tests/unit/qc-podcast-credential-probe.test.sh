#!/usr/bin/env bash
# tests/unit/qc-podcast-credential-probe.test.sh
#
# U031 — the Skill-58 install QC gate's bounded Podbean credential probe.
#
# F31: the pre-U031 gate checked only that PODBEAN_CLIENT_ID / _SECRET were
# non-empty, so a wrong or expired pair passed the gate and failed at first
# publish. The gate now mints a client_credentials token (the exact call
# podbean_publish.sh makes in LOCAL mode) and fails when the pair is
# rejected. This test points the probe at a MOCK token endpoint via
# podbean_publish.sh's own PODBEAN_API_BASE seam (a curl shim first on PATH)
# and proves, hermetically:
#
#   1. an accepting endpoint  → the gate exits 0 with the probe PASS line
#   2. a rejecting endpoint   → the gate exits 1 with the probe FAIL line
#   3. credential values are NEVER printed by the gate (SET/NOT-SET only)
#   4. the probe actually calls {PODBEAN_API_BASE}/oauth/token with HTTP
#      Basic auth (-u) — i.e. it validates the PAIR, not just presence
#   5. the probe is bounded (curl -m timeout flag) so a dead endpoint
#      cannot hang the gate
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$REPO_ROOT/58-podcast-production-engine/qc-podcast.sh"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== qc-podcast-credential-probe.test.sh ==="

[ -f "$GATE" ] || { echo "FAIL: gate not found at $GATE"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- hermetic environment ----------------------------------------------------
# HOME points at a temp tree so resolve_platform_paths resolves SECRETS_ENV
# into the sandbox (absent → skipped) and SKILLS_DIR_DEFAULT into a folder we
# create, so the skill-folder presence assert passes deterministically.
mkdir -p "$WORK/home/.openclaw/skills/58-podcast-production-engine" "$WORK/bin"

# Mock curl: logs its argv (one arg per line) and answers the token endpoint
# per the mode file — accept → a valid token JSON; anything else → the
# invalid_client error body Podbean returns for a bad pair (HTTP-level 401,
# which curl without -f still exits 0 on — the gate decides on the BODY).
cat > "$WORK/bin/curl" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$@" > "${MOCK_LOG:-/dev/null}"
url="${@: -1}"
case "$url" in
  */oauth/token)
    if [ "$(cat "${MOCK_MODE_FILE:-/dev/null}" 2>/dev/null)" = "accept" ]; then
      printf '{"access_token":"mock-token-abc123","token_type":"bearer","expires_in":3600}\n'
    else
      printf '{"error":"invalid_client","error_description":"bad client credentials"}\n'
    fi
    ;;
  *) printf '{}\n' ;;
esac
MOCK
chmod +x "$WORK/bin/curl"

run_gate() {  # $1 = mock mode (accept | reject); echoes the gate's exit code
  echo "$1" > "$WORK/mode"
  HOME="$WORK/home" \
  PATH="$WORK/bin:$PATH" \
  PODBEAN_CLIENT_ID="test-client-id" \
  PODBEAN_CLIENT_SECRET="test-secret-value" \
  PODBEAN_API_BASE="http://mock.invalid/v1" \
  MOCK_MODE_FILE="$WORK/mode" MOCK_LOG="$WORK/curl-args.log" \
  bash "$GATE" > "$WORK/out.log" 2>&1
  echo $?
}

# 1. accepting endpoint → gate passes
rc=$(run_gate accept)
if [ "$rc" = "0" ]; then pass "accepting token endpoint → gate exits 0"
else fail "accepting token endpoint → gate exits 0 (got rc=$rc: $(tail -3 "$WORK/out.log" | tr '\n' ' '))"; fi
if grep -q "PASS — Podbean credential pair mints" "$WORK/out.log"; then
  pass "accept → probe PASS line present"
else fail "accept → probe PASS line present"; fi

# 2. rejecting endpoint → gate fails (the F31 fix: bad creds fail the GATE,
#    not the first publish attempt)
rc=$(run_gate reject)
if [ "$rc" = "1" ]; then pass "rejecting token endpoint → gate exits 1"
else fail "rejecting token endpoint → gate exits 1 (got rc=$rc)"; fi
if grep -q "FAIL — Podbean credential pair mints" "$WORK/out.log"; then
  pass "reject → probe FAIL line present"
else fail "reject → probe FAIL line present"; fi

# 3. AC5: the gate never prints credential values (SET/NOT-SET pattern only)
if grep -qE "test-secret-value|test-client-id" "$WORK/out.log"; then
  fail "gate output never prints credential values"
else pass "gate output never prints credential values"; fi

# 4. the probe validates the PAIR: HTTP Basic auth to the token endpoint
if grep -qx -- "-u" "$WORK/curl-args.log"; then
  pass "probe calls curl with HTTP Basic auth (-u)"
else fail "probe calls curl with HTTP Basic auth (-u)"; fi
if grep -qx "http://mock.invalid/v1/oauth/token" "$WORK/curl-args.log"; then
  pass "probe targets {PODBEAN_API_BASE}/oauth/token"
else fail "probe targets {PODBEAN_API_BASE}/oauth/token"; fi

# 5. AC4: the probe is bounded (curl -m timeout) so it cannot hang the gate
if grep -qx -- "-m" "$WORK/curl-args.log"; then
  pass "probe is bounded (curl -m timeout flag)"
else fail "probe is bounded (curl -m timeout flag)"; fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ $FAIL -gt 0 ] && exit 1 || exit 0
