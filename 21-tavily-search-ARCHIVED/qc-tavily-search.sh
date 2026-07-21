#!/usr/bin/env bash
# Skill 21 — Tavily Search — Install QC
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
: "${TAVILY_API_KEY:=}"

echo ""
echo "═══ Skill 21 — Tavily Search — Install QC ═══"
echo ""
assert "Skill 21 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/21-tavily-search\" ]"
assert "TAVILY_API_KEY set" "[ -n \"$TAVILY_API_KEY\" ]"
# T1-08: the request body carries the API key. Passing it with -d put the whole
# body — credential included — into this process's argv, where any local process
# could read it from the process table for the lifetime of the request. Nothing
# is printed and no document tells anyone to print anything; the exposure is the
# invocation itself, which is why a documentation review would not find it.
# `--data @-` reads the body from standard input instead, so the key never
# appears in argv. The heredoc is unquoted so $TAVILY_API_KEY still expands.
RESP=$(curl -sS -m 10 -X POST "https://api.tavily.com/search" -H "Content-Type: application/json" \
  --data @- <<JSON 2>/dev/null
{"api_key":"$TAVILY_API_KEY","query":"openclaw test","max_results":1}
JSON
)
warn_only "Tavily API responds" "echo \"$RESP\" | grep -qE 'results|answer'"
warn_only "TOOLS.md references Tavily" "grep -qi 'tavily' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 21 QC FAILED"; exit 1; } || { green "Skill 21 QC PASS"; exit 0; }
