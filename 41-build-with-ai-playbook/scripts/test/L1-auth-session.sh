#!/usr/bin/env bash
# L1-auth-session.sh -- Skill 41 v1.3.0 browser-execution harness, Level 1.
#
# PROPERTY PROVEN: the browser/API executor can establish an AUTHENTICATED session and that
# the session layer FAILS CLOSED on a bad/missing credential. We prove this against a LOCAL
# loopback mock GHL server (lib-harness hf_spawn_mock) -- never a live endpoint, never a real
# key. The fake token is the only credential in play.
#
# Why this proves the property (not just describes it):
#   * A real GET with the correct Bearer + Version returns 200  -> auth wiring works.
#   * The SAME GET with NO Authorization header returns 401      -> the layer rejects, it does
#     not silently proceed unauthenticated (the silent-anonymous failure mode).
#   * The SAME GET with a WRONG token returns 401                -> credential is actually
#     checked, not merely "present".
#   * The fake token NEVER appears in the request log            -> session secrets are not
#     leaked even at the transport layer (paired with L4).
#
# Usage: bash L1-auth-session.sh
# Exit:  0 = all checks pass, 1 = a check failed, 3 = SKIP (python3 unavailable on host).
set -uo pipefail
HF_LEVEL="L1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# lib lives next to the level scripts under scripts/test/.
source "$SCRIPT_DIR/lib-harness.sh"

HF_CHECKS=0; HF_FAILS=0
hf_log "auth/session test (platform: $(hf_os), openclaw-home: $(hf_openclaw_home))"

if ! hf_have_python3; then
  hf_log "SKIP: python3 not available; cannot spawn the loopback mock GHL server."
  hf_log "  (On a real VPS/Mac the image ships python3; this SKIP is a host-tooling gap, not a failure.)"
  exit 3
fi

SB="$(hf_make_sandbox)"
trap 'hf_stop_mock "$SB"; rm -rf "$SB"' EXIT

if ! hf_spawn_mock "$SB"; then
  hf_fail "could not start loopback mock GHL server"
  exit 1
fi
BASE="http://127.0.0.1:$HF_MOCK_PORT"
hf_info "mock GHL up at $BASE (loopback only)"

code_for() {
  # $1 = description of header set; remaining args = curl header flags
  local desc="$1"; shift
  hf_curl -o /dev/null -w '%{http_code}' "$@" "$BASE/locations/TESTLOC/tags"
}

# 1) Correct credential -> 200 (authenticated session established)
c_ok="$(code_for "authed" -H "Authorization: Bearer $HF_MOCK_TOKEN" -H "Version: 2021-07-28")"
hf_check "authenticated GET returns 200 (got $c_ok)" test "$c_ok" = "200"

# 2) No Authorization header -> 401 (fails closed, does not proceed anonymous)
c_noauth="$(code_for "no-auth" -H "Version: 2021-07-28")"
hf_check "unauthenticated GET returns 401 (got $c_noauth)" test "$c_noauth" = "401"

# 3) Wrong token -> 401 (credential is actually validated)
c_bad="$(code_for "bad-token" -H "Authorization: Bearer wrong-token" -H "Version: 2021-07-28")"
hf_check "wrong-token GET returns 401 (got $c_bad)" test "$c_bad" = "401"

# 4) Missing Version header -> 401 (GHL requires the API version; session layer enforces it)
c_nover="$(code_for "no-version" -H "Authorization: Bearer $HF_MOCK_TOKEN")"
hf_check "missing-Version GET returns 401 (got $c_nover)" test "$c_nover" = "401"

# 5) The token value must NOT appear anywhere in the transport request log.
leaked="$(grep -F "$HF_MOCK_TOKEN" "$HF_MOCK_REQLOG" 2>/dev/null | wc -l | tr -d ' ')"
hf_check "session secret never written to request log (leaks=$leaked)" test "$leaked" = "0"

# 6) The loopback guardrail itself works: a non-loopback URL is refused by hf_curl.
if hf_curl -o /dev/null -w '%{http_code}' "https://services.leadconnectorhq.com/x" >/dev/null 2>&1; then
  hf_check "loopback guardrail blocks live-host calls" false
else
  hf_check "loopback guardrail blocks live-host calls" true
fi

hf_log "checks=$HF_CHECKS fails=$HF_FAILS"
if [[ $HF_FAILS -eq 0 ]]; then hf_pass "auth/session proven (authed 200; fails closed on no/bad/no-version; no secret leak; guardrail bites)"; exit 0; fi
hf_fail "$HF_FAILS auth/session check(s) failed"; exit 1
