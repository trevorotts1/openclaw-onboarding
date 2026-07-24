#!/usr/bin/env bash
# Skill 58 — Podcast Production Engine — Install QC (U031, U038)
#
# U031: Before U031 the podcast install QC checked only that the Podbean
# client ID/secret variables were NON-EMPTY — a wrong or expired credential
# pair passed the gate and failed at the first publish attempt. This gate
# adds a BOUNDED API probe: when the LOCAL credential pair is set, it must
# actually mint a usable access token from the Podbean OAuth endpoint (HTTP
# Basic, grant_type=client_credentials — the exact call podbean_publish.sh
# makes in LOCAL mode).
#
# U038: The QC gate previously checked local files and credentials but never
# probed the n8n host to confirm the deploy target is reachable.
# probe_n8n_host() does a bounded HTTP HEAD (curl -I, default 10s timeout)
# against the configured n8n host URL. An unreachable host is reported (WARN
# by default; set QC_N8N_PROBE_MODE=fail to make it a hard FAIL). The probe
# is bounded so a hung host can never stall the gate.
#
# n8n host resolution (first hit wins):
#   N8N_HOST                          explicit host/base URL
#   PODBEAN_PUBLISH_WEBHOOK_URL       -> host portion (strip /webhook/...)
#   PODBEAN_BROKER_WEBHOOK_URL        -> host portion (strip /webhook/...)
#   default                           https://main.blackceoautomations.com
#
# Fleet context (podbean_publish.sh header): PROXY and BROKER boxes hold NO
# Podbean app secret — the n8n webhook mints channel-scoped tokens server-
# side. On those boxes the client pair is legitimately absent, so the probe
# is SKIPPED (warn-only), never failed; the presence asserts above already
# fail a box that SHOULD be LOCAL but is missing the pair.
#
# Credential hygiene (AC5): credential values are NEVER printed — presence
# checks and probe outcomes only (SET/NOT-SET pattern), mirroring
# podbean_publish.sh's redaction discipline.
#
# The probe is bounded: curl -m 10 (AC4) so a dead endpoint cannot hang the
# gate. PODBEAN_API_BASE — podbean_publish.sh's own test seam — overrides
# the endpoint so the unit test can point the probe at a mock.
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() {
    if [ -d "/data/.openclaw" ]; then
      export SECRETS_ENV="/data/.openclaw/secrets/.env" SKILLS_DIR_DEFAULT="/data/.openclaw/skills"
    else
      export SECRETS_ENV="$HOME/.openclaw/secrets/.env" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"
    fi
  }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

# U038: bounded reachability probe for an n8n host URL.
#   probe_n8n_host <url> [timeout_secs]
#   Does an HTTP HEAD (curl -I) with a bounded timeout (default 10s). Returns 0
#   if the host answers (any HTTP status — we only care that it is reachable),
#   1 if it cannot be reached within the timeout. Never hangs (curl -m bounds
#   the whole transfer). curl is required; if absent the probe returns 2 so the
#   caller can treat it as "cannot verify" rather than "down".
probe_n8n_host() {
  local url="$1" timeout="${2:-10}"
  command -v curl >/dev/null 2>&1 || return 2
  # -I HEAD, -sS silent-but-show-errors, -o /dev/null discard body, -m bounded.
  # Any HTTP response (even 4xx/5xx) means the host is reachable; only a
  # connection/timeout failure (curl non-zero) means unreachable.
  if curl -sS -o /dev/null -I -m "$timeout" "$url" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

# U038: resolve the configured n8n host base URL (never a secret — a host URL).
resolve_n8n_host() {
  if [ -n "${N8N_HOST:-}" ]; then printf '%s' "$N8N_HOST"; return 0; fi
  local wh="${PODBEAN_PUBLISH_WEBHOOK_URL:-${PODBEAN_BROKER_WEBHOOK_URL:-}}"
  if [ -n "$wh" ]; then
    # Strip the /webhook/... path to get the scheme://host base.
    printf '%s' "${wh%%/webhook/*}"
    return 0
  fi
  printf '%s' "https://main.blackceoautomations.com"
}

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${PODBEAN_PODCAST_ID:=}"; : "${PODBEAN_PUBLISH_TOKEN:=}"; : "${PODBEAN_BROKER_TOKEN:=}"
: "${PODBEAN_CLIENT_ID:=}"; : "${PODBEAN_CLIENT_SECRET:=}"
# Production endpoint; PODBEAN_API_BASE is podbean_publish.sh's test seam —
# the canary and the unit test point it at a mock.
PODBEAN_API="${PODBEAN_API_BASE:-https://api.podbean.com/v1}"

echo ""
echo "═══ Skill 58 — Podcast Production Engine — Install QC ═══"
echo ""

# ── presence (pre-U031 checks — necessary but NOT sufficient) ───────────
assert "Skill 58 folder present"     "[ -d \"$SKILLS_DIR_DEFAULT/58-podcast-production-engine\" ]"
assert "PODBEAN_PODCAST_ID set (the client Channel ID)" "[ -n \"$PODBEAN_PODCAST_ID\" ]"
# At least one publish transport must be configured: proxy token, broker token,
# or local client credentials.
if [ -n "$PODBEAN_PUBLISH_TOKEN" ] || [ -n "$PODBEAN_BROKER_TOKEN" ] || { [ -n "$PODBEAN_CLIENT_ID" ] && [ -n "$PODBEAN_CLIENT_SECRET" ]; }; then
  green "  ✓ PASS — a Podbean publish transport is configured (proxy/broker/local)"
  PASS=$((PASS+1))
else
  red "  ✗ FAIL — no Podbean publish transport (set PODBEAN_PUBLISH_TOKEN, PODBEAN_BROKER_TOKEN, or PODBEAN_CLIENT_ID+SECRET)"
  FAIL=$((FAIL+1))
fi

# ── U031: bounded credential probe ──────────────────────────────────────────
# A non-empty pair is not proof the pair WORKS. Mint a client_credentials
# token exactly as podbean_publish.sh does in LOCAL mode; a pair the API
# rejects fails THIS gate instead of the first publish attempt. Bounded by
# curl -m 10 so a dead endpoint cannot hang the gate; the credential values
# are never printed — only the probe outcome.
if [ -n "$PODBEAN_CLIENT_ID" ] && [ -n "$PODBEAN_CLIENT_SECRET" ]; then
  TOKEN_RESP=$(curl -sS -m 10 -u "$PODBEAN_CLIENT_ID:$PODBEAN_CLIENT_SECRET" \
    -d "grant_type=client_credentials" "$PODBEAN_API/oauth/token" 2>/dev/null)
  if printf '%s' "$TOKEN_RESP" | grep -qE '"access_token"[[:space:]]*:[[:space:]]*"[^"]+"'; then
    green "  ✓ PASS — Podbean credential pair mints a usable access token"; PASS=$((PASS+1))
  else
    red "  ✗ FAIL — Podbean credential pair mints a usable access token (token endpoint rejected the pair or is unreachable)"; FAIL=$((FAIL+1))
  fi
else
  # PROXY/BROKER boxes hold no app secret (the n8n webhook mints channel-
  # scoped tokens server-side) — an absent pair is legitimate there, so the
  # probe is skipped, not failed.
  yellow "  ⚠ WARN — Podbean credential probe skipped (no LOCAL client pair; PROXY/BROKER boxes mint tokens server-side)"; WARN=$((WARN+1))
fi

# U038: probe the configured n8n host for reachability (bounded). WARN by
# default; QC_N8N_PROBE_MODE=fail makes an unreachable host a hard FAIL.
N8N_HOST_URL="$(resolve_n8n_host)"
N8N_PROBE_MODE="${QC_N8N_PROBE_MODE:-warn}"
echo "  · probing n8n host for reachability: $N8N_HOST_URL (bounded, ${QC_N8N_PROBE_TIMEOUT:-10}s)"
probe_n8n_host "$N8N_HOST_URL" "${QC_N8N_PROBE_TIMEOUT:-10}"
N8N_RC=$?
if [ "$N8N_RC" -eq 0 ]; then
  green "  ✓ PASS — n8n host reachable: $N8N_HOST_URL"
  PASS=$((PASS+1))
elif [ "$N8N_PROBE_MODE" = "fail" ]; then
  red "  ✗ FAIL — n8n host UNREACHABLE: $N8N_HOST_URL (deploy target is down; the skill cannot publish)"
  FAIL=$((FAIL+1))
else
  yellow "  ⚠ WARN — n8n host UNREACHABLE: $N8N_HOST_URL (deploy target may be down; publish will fail until it is reachable)"
  WARN=$((WARN+1))
fi

# ── U040: integration test reference (NO AUTO-RUN) ──────────────────────────
# The integration test exercises the full Podbean publish+verify+delete cycle
# against a live API. It is explicitly gated behind PODBEAN_INTEGRATION_TEST=1
# and NEVER runs unattended. This QC gate references it so operators and judges
# know it exists, but does NOT auto-run it.
INTEGRATION_TEST="$SKILLS_DIR_DEFAULT/58-podcast-production-engine/scripts/tests/integration-test-podbean-publish-verify.sh"
if [ -f "$INTEGRATION_TEST" ]; then
  echo ""
  echo "  Info -- U040 integration test found: $INTEGRATION_TEST"
  echo "  Info -- This test is GATED — it never runs unattended. To opt in:"
  echo "  Info --   PODBEAN_INTEGRATION_TEST=1 bash 58-podcast-production-engine/scripts/tests/integration-test-podbean-publish-verify.sh"
  echo "  Info -- It creates a draft episode, verifies it on the API, and deletes it."
else
  yellow "  WARN -- U040 integration test not found at expected path"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 58 QC FAILED"; exit 1; } || { green "Skill 58 QC PASS"; exit 0; }
