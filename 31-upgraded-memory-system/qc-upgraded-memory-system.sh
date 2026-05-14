#!/usr/bin/env bash
# Skill 31 — Upgraded Memory System — Install QC (8-layer architecture)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" CONFIG_JSON="$HOME/.openclaw/openclaw.json" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GEMINI_API_KEY:=}"; : "${GOOGLE_API_KEY:=}"

echo ""
echo "═══ Skill 31 — Upgraded Memory System — Install QC ═══"
echo ""
assert "Skill 31 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/31-upgraded-memory-system\" ]"
echo ""
echo "── 8-layer memory architecture ──"
assert "Layer 1: Core .md files exist"  "[ -f \"$WORKSPACE/AGENTS.md\" ] && [ -f \"$WORKSPACE/TOOLS.md\" ] && [ -f \"$WORKSPACE/MEMORY.md\" ]"
warn_only "Layer 2: Memory flush referenced in AGENTS.md" "grep -qiE 'memory flush|flushed' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
warn_only "Layer 3: Session indexing path exists" "[ -d \"$HOME/.openclaw/agents\" ] || [ -d \"~/.openclaw/agents\" ]"
assert "Layer 4: Gemini Embedding 2 configured (Gemini OR Google API key)" "[ -n \"$GEMINI_API_KEY\" ] || [ -n \"$GOOGLE_API_KEY\" ]"
warn_only "Layer 4: gemini-indexer.py present" "find \"$WORKSPACE\" -maxdepth 3 -name 'gemini-indexer.py' 2>/dev/null | head -1 | grep -q ."
warn_only "Layer 5: memory-core plugin enabled" "command -v openclaw && openclaw config get plugins.slots.memory 2>/dev/null | grep -qi 'memory-core'"
warn_only "Layer 6: Cognee installation OR plugin" "ls $HOME/clawd/scripts/cognee-bridge.py 2>/dev/null || docker ps 2>/dev/null | grep -qi cognee"
warn_only "Layer 7: Obsidian Vault configured" "command -v openclaw && openclaw config get plugins.entries.obsidian-vault 2>/dev/null | grep -qiE 'vault|path'"
warn_only "Layer 8: Active Memory enabled" "command -v openclaw && openclaw config get plugins.entries.active-memory.enabled 2>/dev/null | grep -qi true"
warn_only "memorySearch provider set to gemini" "command -v openclaw && openclaw config get agents.defaults.memorySearch.provider 2>/dev/null | grep -qi gemini"
warn_only "DREAMS.md exists" "[ -f \"$WORKSPACE/DREAMS.md\" ]"
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 31 QC FAILED"; exit 1; } || { green "Skill 31 QC PASS"; exit 0; }
