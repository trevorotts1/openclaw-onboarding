#!/usr/bin/env bash
# ============================================================
#  22-book-to-persona-coaching-leadership-system — Install QC Script (v9.3.0 generic)
#  Generic baseline QC. Skill-specific tests should be added below.
#  Exits 0 if assertions pass. Non-zero = blocker.
# ============================================================

set -u
PASS=0; FAIL=0; WARN=0

SKILL_DIR="$(dirname "$0")"
SKILL_NAME="$(basename "$SKILL_DIR")"

LIB="$SKILL_DIR/../lib-shared.sh"
[ -f "$LIB" ] || LIB="$HOME/.openclaw/skills/lib-shared.sh"
[ -f "$LIB" ] && source "$LIB"

if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() {
    if [ -d "/data/.openclaw" ]; then
      export OPENCLAW_PLATFORM="vps"
      export SECRETS_ENV="/data/.openclaw/secrets/.env"
      export WORKSPACE="/data/clawd"
      export SKILLS_DIR_DEFAULT="/data/.openclaw/skills"
    else
      export OPENCLAW_PLATFORM="mac"
      export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
      export WORKSPACE="$HOME/clawd"
      export SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"
    fi
  }
fi
resolve_platform_paths

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }

assert() {
  if eval "$2" >/dev/null 2>&1; then
    green "  ✓ PASS — $1"; PASS=$((PASS+1))
  else
    red "  ✗ FAIL — $1"; FAIL=$((FAIL+1))
  fi
}
warn_only() {
  if eval "$2" >/dev/null 2>&1; then
    green "  ✓ PASS — $1"; PASS=$((PASS+1))
  else
    yellow "  ⚠ WARN — $1"; WARN=$((WARN+1))
  fi
}

echo ""
echo "═══════════════════════════════════════════════"
echo "  $SKILL_NAME — Install QC (v9.3.0 generic)"
echo "═══════════════════════════════════════════════"
echo "  Platform: ${OPENCLAW_PLATFORM:-unknown}"
echo "  Date:     $(date)"
echo ""

echo "── Section A: Skill files present ──"
assert "SKILL.md present"          "[ -f \"$SKILL_DIR/SKILL.md\" ]"
assert "INSTALL.md present"        "[ -f \"$SKILL_DIR/INSTALL.md\" ]"
assert "QC.md present"             "[ -f \"$SKILL_DIR/QC.md\" ]"
warn_only "CORE_UPDATES.md present"      "[ -f \"$SKILL_DIR/CORE_UPDATES.md\" ]"
warn_only "skill-version.txt present"    "[ -f \"$SKILL_DIR/skill-version.txt\" ]"

echo ""
echo "── Section B: Install discipline ──"
warn_only "QC.md has v9.3.0 install-time rubric" "grep -q 'INSTALL-TIME QC RUBRIC' \"$SKILL_DIR/QC.md\""
warn_only "INSTALL.md references INSTALL-CONTRACT.md" "grep -qi 'INSTALL-CONTRACT' \"$SKILL_DIR/INSTALL.md\" 2>/dev/null"

echo ""
echo "── Section C: Skill is reachable from canonical location ──"
assert "Skill folder present in canonical skills dir" \
  "[ -d \"$SKILLS_DIR_DEFAULT/$SKILL_NAME\" ] || [ -d \"$HOME/.openclaw/skills/$SKILL_NAME\" ] || [ -d \"/data/.openclaw/skills/$SKILL_NAME\" ]"

echo ""
echo "── Section D: Security ──"
assert "Secrets file is chmod 600 (or absent)" \
  "[ ! -f \"$SECRETS_ENV\" ] || [ \"$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings"
echo "═══════════════════════════════════════════════"
echo ""
echo "ℹ️  This is the GENERIC v9.3.0 baseline QC. For full functional"
echo "    coverage, the agent should also run the checklist items in"
echo "    QC.md and score against the 0-10 rubric (8.5+ to pass)."
echo ""

if [ "$FAIL" -gt 0 ]; then
  red "Generic QC FAILED. Fix failures and re-run."
  exit 1
else
  green "Generic QC PASS. Full QC.md rubric still required for 8.5+ scoring."
  exit 0
fi
