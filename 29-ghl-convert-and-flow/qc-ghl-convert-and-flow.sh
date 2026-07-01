#!/usr/bin/env bash
# Skill 29 — GHL Convert and Flow API — Install QC (Tier 3 reference)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

# --- Load + resolve credentials. Canonical = GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_LOCATION_ID,
#     the SAME names the runnable examples use. Legacy aliases are mapped on so old setups pass.
#     Container/VPS already has the vars in env (the [ -f ] guard just skips the file load). ---
if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GOHIGHLEVEL_API_KEY:=${GHL_API_KEY:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-}}}}}"
: "${GOHIGHLEVEL_LOCATION_ID:=${GHL_LOCATION_ID:-}}"

# Self-locate the skill dir (works in both repo and installed layouts).
S29="$SKILLS_DIR_DEFAULT/29-ghl-convert-and-flow"
[ -f "$SKILL_DIR/SKILL.md" ] && S29="$SKILL_DIR"

echo ""
echo "═══ Skill 29 — GHL Convert and Flow API — Install QC ═══"
echo ""
assert "Skill 29 folder present" "[ -d \"$S29\" ]"
assert "references/ subfolder present (Tier 3 lookup files)" "[ -d \"$S29/references\" ]"
assert "GOHIGHLEVEL_API_KEY (PIT) resolved"  "[ -n \"$GOHIGHLEVEL_API_KEY\" ]"
assert "GOHIGHLEVEL_LOCATION_ID resolved"    "[ -n \"$GOHIGHLEVEL_LOCATION_ID\" ]"
assert "Token has pit- prefix (documented PIT format)" "[[ \"$GOHIGHLEVEL_API_KEY\" == pit-* ]]"

# --- No shipped example may reference an unset LEGACY \$VAR (it would fire an empty Bearer).
#     Matches '\$NAME' usage only; the resolver's '\${NAME:-...}' alias form is NOT flagged. ---
LEGACY_RE='\$(GHL_API_KEY|GHL_LOCATION_ID|PRIVATE_INTEGRATION_TOKEN|GHL_PRIVATE_INTEGRATION_TOKEN|GHL_PRIVATE_TOKEN)'
# CHANGELOG.md legitimately names the old vars when describing the fix — exclude it.
if grep -rEl "$LEGACY_RE" "$S29" --include='*.md' --exclude='CHANGELOG.md' >/dev/null 2>&1; then
  red "  ✗ FAIL — a shipped example uses a legacy \$VAR (canonical: \$GOHIGHLEVEL_API_KEY / \$GOHIGHLEVEL_LOCATION_ID):"
  grep -rEn "$LEGACY_RE" "$S29" --include='*.md' --exclude='CHANGELOG.md' 2>/dev/null | sed 's/^/        /' | head -20
  FAIL=$((FAIL+1))
else
  green "  ✓ PASS — no shipped example uses a legacy \$VAR (all canonical)"; PASS=$((PASS+1))
fi

# --- Live, network-gated location read. Uses Version 2021-07-28 so a 200 also proves the
#     token is LOCATION-scoped (media-capable); an agency PIT 401s here just as it does on media. ---
if [ -n "$GOHIGHLEVEL_API_KEY" ] && [ -n "$GOHIGHLEVEL_LOCATION_ID" ]; then
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 8 -m 20 \
    -H "Authorization: Bearer $GOHIGHLEVEL_API_KEY" \
    -H "Version: 2021-07-28" \
    "https://services.leadconnectorhq.com/locations/$GOHIGHLEVEL_LOCATION_ID" 2>/dev/null || echo "000")
  case "$CODE" in
    200) green  "  ✓ PASS — live GET /locations/{id} = 200 (LOCATION PIT valid, media-capable)"; PASS=$((PASS+1));;
    401) red    "  ✗ FAIL — live read = 401 (invalid token, or an AGENCY PIT — agency PITs 401 on media)"; FAIL=$((FAIL+1));;
    403) yellow "  ⚠ WARN — live read = 403 (token valid but missing the locations scope)"; WARN=$((WARN+1));;
    000) yellow "  ⚠ WARN — live read skipped (offline / network blocked)"; WARN=$((WARN+1));;
    *)   yellow "  ⚠ WARN — live read returned HTTP $CODE"; WARN=$((WARN+1));;
  esac
else
  yellow "  ⚠ WARN — live read skipped (credentials unresolved)"; WARN=$((WARN+1))
fi

warn_only "Master reference file in master-files folder" \
  "find $HOME/Downloads ~/Downloads -maxdepth 4 -name '*GoHighLevel*Master Reference*.md' -o -name '*Convert and Flow*Master Reference*.md' 2>/dev/null | head -1 | grep -q ."
warn_only "SKILL.md identifies this as Tier 3" "grep -qiE 'tier 3|tier.*36|skill 36' \"$S29/SKILL.md\" 2>/dev/null"
warn_only "jq installed" "command -v jq"
assert "Python 3 installed" "command -v python3"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 29 QC FAILED"; exit 1; } || { green "Skill 29 QC PASS"; exit 0; }
