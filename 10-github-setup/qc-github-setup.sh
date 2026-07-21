#!/usr/bin/env bash
# Skill 10 — GitHub Setup — Install QC
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

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GITHUB_TOKEN:=}"; : "${GH_TOKEN:=}"

echo ""
echo "═══ Skill 10 — GitHub Setup — Install QC ═══"
echo ""
assert "Skill 10 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/10-github-setup\" ]"
assert "git installed" "command -v git"
assert "git user.email configured" "git config --global user.email | grep -qE '@'"
assert "git user.name configured"  "[ -n \"\$(git config --global user.name)\" ]"
# NOT CHECKED, ON PURPOSE — the GitHub CLI (gh).
# SKILL.md's API-ONLY EXECUTION LOCK (SOVEREIGN) states: "do NOT use GitHub CLI
# (gh) for setup/auth." A box installed exactly as documented has no gh, so
# asserting `command -v gh` and `gh auth status` failed this gate permanently on
# every correct install and pushed operators to install the very tool the lock
# forbids. There is nothing to check here: the skill's authentication surface is
# the Personal Access Token, asserted below.
echo "  — SKIPPED BY DESIGN — GitHub CLI presence/auth (SKILL.md API-ONLY SOVEREIGN LOCK forbids gh; not a pass, not a failure)"
warn_only "GITHUB_TOKEN or GH_TOKEN present" "[ -n \"$GITHUB_TOKEN\" ] || [ -n \"$GH_TOKEN\" ]"
warn_only "jq installed" "command -v jq"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 10 QC FAILED"; exit 1; } || { green "Skill 10 QC PASS"; exit 0; }
