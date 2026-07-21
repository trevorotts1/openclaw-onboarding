#!/usr/bin/env bash
# Skill 19 — Humanizer — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

echo ""
echo "═══ Skill 19 — Humanizer — Install QC ═══"
echo ""
assert "Skill 19 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/19-humanizer\" ]"
# T0-61 — INVERTED PREDICATE, FIXED.
#   Was: grep -qE 'em dash|—' over AGENTS.md + SOUL.md.
#   The pattern alternated the RULE PHRASE with the BANNED CHARACTER ITSELF, so a
#   workspace file containing an em dash anywhere in unrelated prose satisfied the
#   check with no ban rule installed at all — the exact state the check exists to
#   detect was the state that made it pass. The literal character is gone from the
#   pattern: this now matches RULE LANGUAGE ONLY.
#   The file set is also corrected. 19-humanizer/CORE_UPDATES.md lists AGENTS.md and
#   TOOLS.md as the files this skill may write and SOUL.md under "Non-relevant (do
#   not edit)", so the check no longer reads a file the skill is forbidden to install
#   its rule into.
#   Still warn_only: promoting it to an assertion is B10/B4 territory and is
#   deliberately NOT bundled here, so this change cannot move the verdict.
warn_only "AGENTS.md or TOOLS.md carries the em-dash ban rule" "grep -qiE 'em[[:space:]-]?dash(es)?' \"$WORKSPACE/AGENTS.md\" \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
warn_only "AGENTS.md or SOUL.md bans AI-tell phrases" "grep -qiE 'as an AI|large language model|AI tell|humaniz' \"$WORKSPACE/AGENTS.md\" \"$WORKSPACE/SOUL.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 19 QC FAILED"; exit 1; } || { green "Skill 19 QC PASS"; exit 0; }
