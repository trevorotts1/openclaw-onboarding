#!/usr/bin/env bash
# Skill 63 — Agnes Image 2.1 Flash — Install QC
#
# Verifies the skill shipped correctly AND that its endpoint reference is
# internally correct (right model, right endpoint, the response_format gotcha,
# the output-dimension table). The content assertions are the ones that can go
# RED on a real defect: corrupt agnes-image-full.md (wrong model/endpoint, drop
# the gotcha or the dimension table) and this script exits 1.
#
# Read-only: it never restarts the gateway, never writes credentials, and never
# prints a secret value (it checks AGNES_AI_API_KEY presence only, as a WARNING).
#
# Exit 0 = all hard checks pass. Exit 1 = at least one hard check failed.
set -u
PASS=0; FAIL=0; WARN=0

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REF="$SKILL_DIR/agnes-image-full.md"

LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths

red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

# Load the environment (name presence only; value is never printed anywhere)
if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${AGNES_AI_API_KEY:=}"

echo ""
echo "═══ Skill 63 — Agnes Image 2.1 Flash — Install QC ═══"
echo ""

# ── Structural: required files present ───────────────────────────────────────
assert "SKILL.md present"            "[ -f \"$SKILL_DIR/SKILL.md\" ]"
assert "INSTRUCTIONS.md present"     "[ -f \"$SKILL_DIR/INSTRUCTIONS.md\" ]"
assert "EXAMPLES.md present"         "[ -f \"$SKILL_DIR/EXAMPLES.md\" ]"
assert "INSTALL.md present"          "[ -f \"$SKILL_DIR/INSTALL.md\" ]"
assert "CORE_UPDATES.md present"     "[ -f \"$SKILL_DIR/CORE_UPDATES.md\" ]"
assert "PREREQS.json present"        "[ -f \"$SKILL_DIR/PREREQS.json\" ]"
assert "full reference present"      "[ -f \"$REF\" ]"

# ── Content correctness of the endpoint reference (these can FIRE red) ────────
assert "reference names model agnes-image-2.1-flash" \
  "grep -qF 'agnes-image-2.1-flash' \"$REF\""
assert "reference names endpoint apihub.agnes-ai.com/v1/images/generations" \
  "grep -qF 'apihub.agnes-ai.com/v1/images/generations' \"$REF\""
assert "reference documents response_format in extra_body (the gotcha)" \
  "grep -qF 'extra_body.response_format' \"$REF\""
assert "reference states image-to-image needs no tags" \
  "grep -qiE 'no[t]? *(require|need).*tags|image-to-image (needs|requires) NO' \"$REF\""
assert "reference carries the output-dimension table (16:9 2K = 2624x1472)" \
  "grep -qF '2624x1472' \"$REF\""
assert "reference marks the endpoint SYNCHRONOUS" \
  "grep -qiF 'synchronous' \"$REF\""

# ── PREREQS.json uses the enforceable {\"skill\":...} form, not {\"skillId\":N} ──
assert "PREREQS.json uses enforceable skill-folder check form" \
  "grep -qF '\"skill\": \"01-teach-yourself-protocol\"' \"$SKILL_DIR/PREREQS.json\""
assert "PREREQS.json does NOT use the silently-ignored skillId form" \
  "! grep -qF 'skillId' \"$SKILL_DIR/PREREQS.json\""

# ── No real credential value leaked into the reference ───────────────────────
# The only key-like token allowed is the literal placeholder YOUR_API_KEY.
assert "no bearer token value hardcoded in the reference" \
  "! grep -qiE 'Bearer[[:space:]]+(sk-|agnes-|[A-Za-z0-9_-]{24,})' \"$REF\" || grep -qF 'Bearer YOUR_API_KEY' \"$REF\""

# ── Soft checks: credential + wiring (WARN, never hard-fail here) ─────────────
warn_only "AGNES_AI_API_KEY set (existing fleet credential; value never printed)" \
  "[ -n \"$AGNES_AI_API_KEY\" ]"
warn_only "TOOLS.md references Agnes" \
  "grep -qi 'agnes' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 63 QC FAILED"; exit 1; } || { green "Skill 63 QC PASS"; exit 0; }
