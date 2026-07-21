#!/usr/bin/env bash
# Skill 64 — Agnes Video V2.0 — Install QC
#
# Hard ASSERTs (each can return a failing exit code on a real defect):
#   - the skill's own files are present next to this script
#   - the full reference names the model, the create endpoint, the recommended
#     poll endpoint, and the num_frames rules
# WARN-only (never fails the build; environment/on-box concerns):
#   - AGNES_AI_API_KEY present (SET/NOT-SET only — the value is NEVER printed)
#   - secrets file mode, endpoint reachability, TOOLS.md pointer, installed folder
#
# Exit 0 = all hard asserts pass. Exit 1 = at least one hard assert failed.
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${AGNES_AI_API_KEY:=}"

REF="$SKILL_DIR/agnes-video-full.md"

echo ""
echo "═══ Skill 64 — Agnes Video V2.0 — Install QC ═══"
echo ""

# ── Hard asserts: skill files present (evaluated against this script's folder) ──
assert "SKILL.md present" "[ -f \"$SKILL_DIR/SKILL.md\" ]"
assert "INSTRUCTIONS.md present" "[ -f \"$SKILL_DIR/INSTRUCTIONS.md\" ]"
assert "EXAMPLES.md present" "[ -f \"$SKILL_DIR/EXAMPLES.md\" ]"
assert "INSTALL.md present" "[ -f \"$SKILL_DIR/INSTALL.md\" ]"
assert "CORE_UPDATES.md present" "[ -f \"$SKILL_DIR/CORE_UPDATES.md\" ]"
assert "full reference agnes-video-full.md present" "[ -f \"$REF\" ]"

# ── Hard asserts: the reference documents the real API surface ──
assert "reference names model agnes-video-v2.0" "grep -q 'agnes-video-v2.0' \"$REF\""
assert "reference documents create endpoint /v1/videos" "grep -q '/v1/videos' \"$REF\""
assert "reference documents recommended poll agnesapi?video_id" "grep -q 'agnesapi?video_id' \"$REF\""
assert "reference documents the 8n rule for num_frames" "grep -q '8n' \"$REF\""
assert "reference documents the 441 num_frames cap" "grep -q '441' \"$REF\""

# ── Warn-only: environment / on-box concerns (never fail the build) ──
warn_only "AGNES_AI_API_KEY set (SET/NOT-SET only; value never printed)" "[ -n \"$AGNES_AI_API_KEY\" ]"
warn_only "secrets file chmod 600" "[ \"\$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
warn_only "installed skills dir carries 64-agnes-video" "[ -d \"$SKILLS_DIR_DEFAULT/64-agnes-video\" ]"
if [ -n "$AGNES_AI_API_KEY" ]; then
  RESP=$(curl -sS -m 10 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $AGNES_AI_API_KEY" "https://apihub.agnes-ai.com/agnesapi?video_id=qc-probe" 2>/dev/null)
  warn_only "apihub.agnes-ai.com reachable (any HTTP status)" "[ -n \"$RESP\" ] && [ \"$RESP\" != '000' ]"
else
  yellow "  ⚠ WARN — endpoint reachability skipped (no key on this box)"; WARN=$((WARN+1))
fi
warn_only "TOOLS.md references agnes" "grep -qi 'agnes' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 64 QC FAILED"; exit 1; } || { green "Skill 64 QC PASS"; exit 0; }
