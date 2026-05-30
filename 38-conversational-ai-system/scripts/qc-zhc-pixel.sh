#!/usr/bin/env bash
# qc-zhc-pixel.sh — machine-enforce the ZHC Pixel (Feature 49) invariants from the
# repo alone (CI-safe, BASH-only so it respects qc-static's .py claude-/anthropic ban).
#
# Asserts:
#   1. The pixel JS template exists with the three placeholders, and the generator
#      (27-render-pixel-js.sh) substitutes them.
#   2. The OpenClaw hook `pixel-visitor-signal` is REGISTERED by 28-configure-pixel-hook.sh
#      (deliver:false, the bot-gate-first messageTemplate, the scoped Pixel Concierge agent
#      + allow-list prefix hook:pixel:).
#   3. The Pixel Concierge AGENTS.md protocol is present (STEP_1_45_PIXEL_CONCIERGE block
#      in 05-update-agents-md.sh) and the protocol doc exists.
#   4. ZHC- tag prefixes + ZHC_ field prefixes are used (the F49 tag/field set).
#   5. Privacy controls are documented (GDPR consent, CCPA opt-out, DNT, deletion) in
#      BOTH the protocol and the pixel template.
#   6. The scope precheck (26-verify-pixel-prerequisites.sh) exists, names the three
#      scopes, and points at the token-instructions Google Doc; the deploy is GATED.
#   7. No personal/client data in any F49 file (delegates to the BANNED list shape).
#
# Exit codes: 0 = clean; 1 = at least one F49 invariant violated.
#
# Usage:
#   bash scripts/qc-zhc-pixel.sh
#   bash scripts/qc-zhc-pixel.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,34p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

PROTO="$SKILL_DIR/protocols/zhc-pixel-protocol.md"
TEMPLATE="$SKILL_DIR/templates/zhc-pixel/zhc-pixel.template.js"
GEN="$SKILL_DIR/scripts/27-render-pixel-js.sh"
HOOKCFG="$SKILL_DIR/scripts/28-configure-pixel-hook.sh"
PRECHECK="$SKILL_DIR/scripts/26-verify-pixel-prerequisites.sh"
DEPLOY="$SKILL_DIR/scripts/29-deploy-pixel-cloudflare.sh"
AGENTS="$SKILL_DIR/scripts/05-update-agents-md.sh"

echo "=== qc-zhc-pixel: ZHC Pixel (F49) invariant gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

# 1. Pixel JS template + placeholders + generator substitution.
if [ -f "$TEMPLATE" ]; then
  pass "templates/zhc-pixel/zhc-pixel.template.js exists"
  for ph in "__ZHC_PIXEL_ENDPOINT__" "__ZHC_PIXEL_SITE_ID__" "__ZHC_PIXEL_AGENT_ID__"; do
    grep -qF "$ph" "$TEMPLATE" && pass "template has placeholder: $ph" || fail "template MISSING placeholder: $ph"
  done
else
  fail "pixel template MISSING: templates/zhc-pixel/zhc-pixel.template.js"
fi
if [ -f "$GEN" ]; then
  pass "scripts/27-render-pixel-js.sh exists (generator)"
  grep -q '__ZHC_PIXEL_ENDPOINT__' "$GEN" && grep -q '__ZHC_PIXEL_SITE_ID__' "$GEN" && grep -q '__ZHC_PIXEL_AGENT_ID__' "$GEN" \
    && pass "generator substitutes all three placeholders" \
    || fail "generator does not substitute all three placeholders"
  # The generator must guard against an unresolved placeholder leaking into output.
  grep -q 'unresolved placeholder' "$GEN" && pass "generator guards against unresolved placeholders" \
    || fail "generator must guard against unresolved placeholders remaining in output"
else
  fail "generator MISSING: scripts/27-render-pixel-js.sh"
fi

# 2. Hook registration.
if [ -f "$HOOKCFG" ]; then
  pass "scripts/28-configure-pixel-hook.sh exists"
  grep -q 'pixel-visitor-signal' "$HOOKCFG" && pass "hook id pixel-visitor-signal registered" || fail "hook id pixel-visitor-signal NOT registered in 28-configure-pixel-hook.sh"
  grep -q 'deliver:false' "$HOOKCFG" && pass "pixel hook is deliver:false" || fail "pixel hook must be deliver:false"
  grep -q 'hook:pixel:' "$HOOKCFG" && pass "allowed sessionKey prefix hook:pixel: set" || fail "hook:pixel: sessionKey prefix not set"
  grep -qi 'ZERO further reasoning' "$HOOKCFG" && pass "messageTemplate has bot-gate-first (zero reasoning)" || fail "messageTemplate must drop bots with zero reasoning FIRST"
  grep -qi 'NEVER fabricate' "$HOOKCFG" && pass "messageTemplate forbids fabricating identity" || fail "messageTemplate must forbid fabricating visitor identity"
  grep -q 'allowedAgentIds' "$HOOKCFG" && pass "Pixel Concierge added to hooks.allowedAgentIds (scoped allow-list)" || fail "Pixel Concierge must be added to hooks.allowedAgentIds"
  grep -q 'pixel-events' "$HOOKCFG" && pass "F52 data-contract dir (pixel-events) ensured" || fail "27-configure must ensure the pixel-events data-contract dir"
else
  fail "hook configurator MISSING: scripts/28-configure-pixel-hook.sh"
fi

# 3. AGENTS.md Pixel Concierge protocol + protocol doc.
if [ -f "$AGENTS" ] && grep -q 'STEP_1_45_PIXEL_CONCIERGE' "$AGENTS"; then
  pass "05-update-agents-md.sh inserts the STEP_1_45_PIXEL_CONCIERGE block (free slot 1.45)"
else
  fail "05-update-agents-md.sh is missing the STEP_1_45_PIXEL_CONCIERGE block"
fi
if [ -f "$PROTO" ]; then
  pass "protocols/zhc-pixel-protocol.md exists"
  grep -qi 'Pixel Concierge' "$PROTO" && pass "protocol documents the Pixel Concierge agent" || fail "protocol must document the Pixel Concierge agent"
  grep -qi 'scope' "$PROTO" && grep -qi 'GATED' "$PROTO" && pass "protocol documents the scope-gated deploy" || fail "protocol must document the scope-gated deploy"
else
  fail "protocols/zhc-pixel-protocol.md MISSING"
fi

# 4. ZHC- tag + ZHC_ field prefixes.
EXPECTED_TAGS=( "ZHC-pixel-visitor" "ZHC-pixel-returning-visitor" "ZHC-pixel-high-intent" )
for t in "${EXPECTED_TAGS[@]}"; do
  grep -rqF "$t" "$PROTO" "$AGENTS" 2>/dev/null && pass "tag present + ZHC-prefixed: $t" || fail "expected ZHC- tag not found: $t"
done
EXPECTED_FIELDS=( "ZHC_first_visit_date" "ZHC_total_visits" "ZHC_pages_viewed" "ZHC_high_intent_signal" )
for fld in "${EXPECTED_FIELDS[@]}"; do
  grep -rqF "$fld" "$PROTO" "$AGENTS" 2>/dev/null && pass "field present + ZHC_-prefixed: $fld" || fail "expected ZHC_ field not found: $fld"
done

# 5. Privacy controls in BOTH the protocol and the template.
#    Protocol: named controls. Template: enforced in code.
for needle in "GDPR" "CCPA" "Do-Not-Track" "delet"; do
  grep -qi "$needle" "$PROTO" 2>/dev/null && pass "protocol documents privacy control: $needle" || fail "protocol must document privacy control: $needle"
done
if [ -f "$TEMPLATE" ]; then
  grep -qi 'doNotTrack' "$TEMPLATE" && pass "template enforces Do-Not-Track" || fail "template must enforce Do-Not-Track"
  grep -qi 'consent' "$TEMPLATE" && pass "template enforces consent (GDPR deferral)" || fail "template must enforce consent deferral"
  grep -qi 'optOut' "$TEMPLATE" && pass "template exposes optOut (CCPA)" || fail "template must expose an opt-out (CCPA)"
  grep -qi 'delete_request' "$TEMPLATE" && pass "template emits delete_request (deletion)" || fail "template must emit a delete_request (deletion path)"
fi

# 6. Scope precheck + gated deploy.
if [ -f "$PRECHECK" ]; then
  pass "scripts/26-verify-pixel-prerequisites.sh exists (precheck)"
  for scope in "Pages:Edit" "Workers Scripts:Edit" "Workers Routes:Edit"; do
    grep -qF "$scope" "$PRECHECK" && pass "precheck names required scope: $scope" || fail "precheck must name required scope: $scope"
  done
  grep -q '1A_U-H-MMLh2mQ_zhzLxK_tKmFyPNb7i0FNvxjJ4SVpo' "$PRECHECK" && pass "precheck points to the token-instructions Google Doc" || fail "precheck must point to the token-instructions Google Doc"
  grep -q 'ZHC_PIXEL_SCOPES_OK' "$PRECHECK" && pass "precheck records ZHC_PIXEL_SCOPES_OK gate flag" || fail "precheck must record the ZHC_PIXEL_SCOPES_OK gate flag"
else
  fail "scope precheck MISSING: scripts/26-verify-pixel-prerequisites.sh"
fi
if [ -f "$DEPLOY" ]; then
  pass "scripts/29-deploy-pixel-cloudflare.sh exists (deploy)"
  grep -q 'ZHC_PIXEL_SCOPES_OK' "$DEPLOY" && grep -qi 'GATED' "$DEPLOY" && pass "deploy is GATED on the precheck flag" || fail "deploy must be GATED on ZHC_PIXEL_SCOPES_OK"
else
  fail "deploy MISSING: scripts/29-deploy-pixel-cloudflare.sh"
fi

# 7. No personal/client data in F49 files. The authoritative banned-identifier scan is
#    qc-no-personal-data.sh (it scans the WHOLE tree, including every F49 file). We
#    DELEGATE to it rather than re-embedding the banned-identifier literal here — if this
#    gate carried that literal, qc-no-personal-data.sh's own tree scan would flag THIS
#    file. qc-no-personal-data.sh is a required, always-shipped Skill 38 gate.
NOPII="$SKILL_DIR/scripts/qc-no-personal-data.sh"
if [ -f "$NOPII" ]; then
  if bash "$NOPII" --no-gen --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
    pass "no personal/client data in the skill tree incl. F49 files (delegated to qc-no-personal-data.sh)"
  else
    fail "qc-no-personal-data.sh found a banned identifier — run it directly: bash scripts/qc-no-personal-data.sh --no-gen"
  fi
else
  fail "qc-no-personal-data.sh not found — cannot verify F49 files are free of personal/client data"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — ZHC Pixel (F49) invariants hold: hook registered, Pixel Concierge protocol present, ZHC-/ZHC_ prefixes, privacy controls documented + enforced, scope precheck + gated deploy, no personal data."
  exit 0
else
  echo "RESULT: FAIL — at least one ZHC Pixel (F49) invariant was violated (see above)."
  exit 1
fi
