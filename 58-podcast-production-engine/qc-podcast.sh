#!/usr/bin/env bash
# Skill 58 — Podcast Production Engine — Install QC (U031)
#
# F31: before U031 the podcast install QC checked only that the Podbean
# client ID/secret variables were NON-EMPTY — a wrong or expired credential
# pair passed the gate and failed at the first publish attempt. This gate
# adds a BOUNDED API probe: when the LOCAL credential pair is set, it must
# actually mint a usable access token from the Podbean OAuth endpoint (HTTP
# Basic, grant_type=client_credentials — the exact call podbean_publish.sh
# makes in LOCAL mode).
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

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${PODBEAN_CLIENT_ID:=}"; : "${PODBEAN_CLIENT_SECRET:=}"; : "${PODBEAN_PODCAST_ID:=}"
# Production endpoint; PODBEAN_API_BASE is podbean_publish.sh's test seam —
# the canary and the unit test point it at a mock.
PODBEAN_API="${PODBEAN_API_BASE:-https://api.podbean.com/v1}"

echo ""
echo "═══ Skill 58 — Podcast Production Engine — Install QC ═══"
echo ""

# ── presence (the pre-U031 checks — necessary but NOT sufficient) ───────────
assert "Skill 58 folder present"     "[ -d \"$SKILLS_DIR_DEFAULT/58-podcast-production-engine\" ]"
assert "Podbean client ID set"       "[ -n \"$PODBEAN_CLIENT_ID\" ]"
assert "Podbean client secret set"   "[ -n \"$PODBEAN_CLIENT_SECRET\" ]"
warn_only "Podbean Channel ID (podcast_id) set" "[ -n \"$PODBEAN_PODCAST_ID\" ]"

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

# ── U040: Podbean E2E integration test reference ────────────────────────────
# This gate does NOT auto-run the integration test. The test requires explicit
# opt-in (PODBEAN_E2E_TEST=1) and performs a live publish+verify+delete cycle
# against the Podbean API. To run it manually:
#   PODBEAN_E2E_TEST=1 bash scripts/tests/integration_podbean_e2e_publish.sh
yellow "  INFO -- Podbean E2E integration test available at: scripts/tests/integration_podbean_e2e_publish.sh"
yellow "          Requires PODBEAN_E2E_TEST=1 to run (never runs unattended)."

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 58 QC FAILED"; exit 1; } || { green "Skill 58 QC PASS"; exit 0; }
