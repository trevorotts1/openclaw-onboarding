#!/usr/bin/env bash
# tests/unit/qc-ghl-setup-legacy-alias-probe.test.sh
#
# REGRESSION GUARD — Skill 05 QC: the resolved PIT must reach the probes (T2-03).
#
# THE FALSE FAIL THIS CLOSES.  qc-ghl-setup.sh resolves the Private Integration
# Token across ELEVEN supported names into $RESOLVED_PIT, and asserts presence
# against that resolved variable -- but both live probes then sent the raw
# canonical $GOHIGHLEVEL_API_KEY as the bearer token.  On a pre-v12 box holding a
# perfectly valid PIT under any of the other TEN legacy names, the presence
# assertion PASSED and both probes then sent "Authorization: Bearer " (empty),
# failing with an authentication error.  The operator got a confident and wrong
# diagnosis: "your credential is bad", about a credential that was fine.
#
# WHAT THIS FILE PROVES (hermetic; a stub `curl` on PATH captures the header --
# no network, no live GoHighLevel call, no real token, no box touched):
#   T1  PIT under a LEGACY name only -> the probe receives that exact token
#   T2  ...and the live location probe therefore PASSES
#   T3  PIT under the CANONICAL name -> unchanged, still reaches the probe
#   T4  NO token under ANY of the eleven names -> the presence assert still
#       FAILS (the gate was not blunted into a no-op)
#   T5  the token VALUE is never printed in the script's output
#
# Exit 0 = pass.  Exit 1 = the false fail regressed, or the gate went blind.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/05-ghl-setup"

# Synthetic fixture token.  Shaped like a PIT so the "starts with pit-" warn_only
# leg behaves realistically.  Not a real credential and never was.
FIXTURE_PIT="pit-fixture-0000aaaa-1111-2222-3333-444455556666"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-ghl-setup-legacy-alias-probe.test.sh (T2-03) ==="
echo ""

if [ ! -f "$SKILL_DIR/qc-ghl-setup.sh" ]; then
  echo "  FAIL: $SKILL_DIR/qc-ghl-setup.sh not found"; exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

strip_ansi() { sed -e 's/\x1b\[[0-9;]*m//g'; }

# Stage the skill WITHOUT a lib-shared.sh sibling so the script's own fallback
# resolve_platform_paths runs and SECRETS_ENV is derived from the fixture HOME.
mkdir -p "$TMP/skills"
cp -R "$SKILL_DIR" "$TMP/skills/05-ghl-setup"
QC="$TMP/skills/05-ghl-setup/qc-ghl-setup.sh"

# ── Stub curl: records the Authorization header, answers like the real API ────
# A non-empty bearer gets a valid location document; an empty bearer gets the
# 401 shape the live API returns.  This is what turns "which token was sent"
# into an observable PASS/FAIL verdict instead of a claim.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/curl" <<'STUB'
#!/usr/bin/env bash
AUTH=""
WANT_CODE=0
prev=""
for a in "$@"; do
  case "$prev" in
    -H) case "$a" in Authorization:*) AUTH="$a" ;; esac ;;
    -w) WANT_CODE=1 ;;
  esac
  prev="$a"
done
printf '%s\n' "$AUTH" >> "$CURL_AUTH_LOG"
TOKEN="${AUTH#Authorization: Bearer }"
if [ -n "$TOKEN" ] && [ "$TOKEN" != "$AUTH" ]; then
  if [ "$WANT_CODE" = "1" ]; then printf '200'; else
    printf '{"id":"fixtureLocationId12345","name":"Fixture Location"}'
  fi
else
  if [ "$WANT_CODE" = "1" ]; then printf '401'; else
    printf '{"message":"Invalid JWT","statusCode":401}'
  fi
fi
exit 0
STUB
chmod +x "$TMP/bin/curl"

# run_case <case-dir> <env-assignment-or-empty>
# Builds a fixture HOME whose secrets file holds ONLY the given assignment,
# runs the gate with the stub curl first on PATH, and echoes the output.
run_case() {
  local name="$1" assignment="$2"
  local home="$TMP/home-$name"
  mkdir -p "$home/.openclaw/secrets" "$home/clawd"
  : > "$home/.openclaw/secrets/.env"
  [ -n "$assignment" ] && printf '%s\n' "$assignment" > "$home/.openclaw/secrets/.env"
  printf 'GOHIGHLEVEL_LOCATION_ID=fixtureLocationId12345\n' >> "$home/.openclaw/secrets/.env"
  chmod 600 "$home/.openclaw/secrets/.env"
  export CURL_AUTH_LOG="$TMP/auth-$name.log"
  : > "$CURL_AUTH_LOG"
  env -i HOME="$home" PATH="$TMP/bin:/usr/bin:/bin" \
      CURL_AUTH_LOG="$CURL_AUTH_LOG" OPENCLAW_PLATFORM=mac \
      /bin/bash "$QC" 2>&1 | strip_ansi
}

verdict_for() {  # <output> <assertion-substring>
  printf '%s\n' "$1" | grep -F -- "$2" | grep -oE '(PASS|FAIL|WARN)' | head -1
}

# ── T1/T2: legacy name only ─────────────────────────────────────────────────
OUT_LEGACY="$(run_case legacy "GHL_PIT=$FIXTURE_PIT")"
AUTH_LEGACY="$(head -1 "$TMP/auth-legacy.log")"

if [ "$AUTH_LEGACY" = "Authorization: Bearer $FIXTURE_PIT" ]; then
  pass "T1 PIT under legacy name GHL_PIT -> probe received the resolved token"
else
  fail "T1 probe received '${AUTH_LEGACY:-<none>}' (expected the resolved token; empty bearer = the T2-03 defect)"
fi

V2="$(verdict_for "$OUT_LEGACY" 'Location endpoint returns valid id')"
if [ "$V2" = "PASS" ]; then
  pass "T2 legacy-name box -> live location probe PASSES (no false 'bad credential')"
else
  fail "T2 legacy-name box -> location probe verdict was '${V2:-<none>}', expected PASS"
fi

# ── T3: canonical name unchanged ────────────────────────────────────────────
OUT_CANON="$(run_case canon "GOHIGHLEVEL_API_KEY=$FIXTURE_PIT")"
AUTH_CANON="$(head -1 "$TMP/auth-canon.log")"
if [ "$AUTH_CANON" = "Authorization: Bearer $FIXTURE_PIT" ]; then
  pass "T3 PIT under the canonical name -> probe still receives it (no regression)"
else
  fail "T3 canonical-name probe received '${AUTH_CANON:-<none>}'"
fi

# ── T4: ANTI-FALSE-POSITIVE — no token anywhere must STILL fail ─────────────
OUT_NONE="$(run_case none "")"
V4="$(verdict_for "$OUT_NONE" 'GHL PIT set (any canonical alias)')"
if [ "$V4" = "FAIL" ]; then
  pass "T4 no token under any of the eleven names -> presence assert still FAILS"
else
  fail "T4 no token -> presence assert returned '${V4:-<none>}', expected FAIL (gate blunted!)"
fi

# ── T5: secret hygiene — the value is never echoed ──────────────────────────
if printf '%s\n' "$OUT_LEGACY$OUT_CANON" | grep -qF "$FIXTURE_PIT"; then
  fail "T5 the token VALUE appeared in the script output"
else
  pass "T5 the token value is never printed (presence/prefix only)"
fi

echo ""
echo "  Result: $PASS passed | $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "qc-ghl-setup-legacy-alias-probe.test.sh: FAILED"
  exit 1
fi
echo "qc-ghl-setup-legacy-alias-probe.test.sh: PASSED"
exit 0
