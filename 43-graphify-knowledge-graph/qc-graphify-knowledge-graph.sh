#!/usr/bin/env bash
# Skill 43 — Graphify Knowledge Graph — Install QC
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR_SELF="$(cd "$(dirname "$0")" && pwd)"
LIB="$SKILL_DIR_SELF/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export WORKSPACE="$HOME/.openclaw/workspace" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

# Surface common tool bins for non-login shells.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"

GR_DIR="$SKILLS_DIR_DEFAULT/43-graphify-knowledge-graph"
# When run from inside the repo (pre-deploy QC), fall back to the skill's own dir.
[ -d "$GR_DIR" ] || GR_DIR="$SKILL_DIR_SELF"

# Resolve the skill version dynamically (no hardcoded literal — a pinned literal went
# stale at 1.0.0 while the file was 1.0.2 and made this gate always-red). The expected
# version is read from SKILL.md frontmatter, the single source the skill loader reads;
# skill-version.txt must be valid semver AND agree with it.
GR_SKILL_VER="$(tr -d '[:space:]' < "$GR_DIR/skill-version.txt" 2>/dev/null)"
GR_FM_VER="$(awk '/^---[[:space:]]*$/{n++; next} n==1 && /^version:/{sub(/^version:[[:space:]]*/,""); gsub(/[[:space:]]/,""); print; exit}' "$GR_DIR/SKILL.md" 2>/dev/null)"

echo ""
echo "═══ Skill 43 — Graphify Knowledge Graph — Install QC ═══"
echo ""

# Structure (10 hard assertions on the shipped folder)
assert "Skill 43 folder present" "[ -d \"$GR_DIR\" ]"
assert "SKILL.md present" "[ -f \"$GR_DIR/SKILL.md\" ]"
assert "INSTALL.md present" "[ -f \"$GR_DIR/INSTALL.md\" ]"
assert "INSTRUCTIONS.md present" "[ -f \"$GR_DIR/INSTRUCTIONS.md\" ]"
assert "CORE_UPDATES.md present" "[ -f \"$GR_DIR/CORE_UPDATES.md\" ]"
assert "CHANGELOG.md present" "[ -f \"$GR_DIR/CHANGELOG.md\" ]"
assert "skill-version.txt present + valid semver (X.Y.Z)" "printf '%s' \"$GR_SKILL_VER\" | grep -qE '^[0-9]+\\.[0-9]+\\.[0-9]+$'"
assert "skill-version.txt matches SKILL.md frontmatter version ($GR_FM_VER)" "[ -n \"$GR_SKILL_VER\" ] && [ \"$GR_SKILL_VER\" = \"$GR_FM_VER\" ]"
assert "references/GRAPHIFY-COMMANDS.md present" "[ -f \"$GR_DIR/references/GRAPHIFY-COMMANDS.md\" ]"
assert "verify-graphify-install.sh present" "[ -f \"$GR_DIR/scripts/verify-graphify-install.sh\" ]"

# Content invariants — the rules that make this skill correct
assert "INSTALL.md uses 'graphifyy[all]' install command" "grep -q 'graphifyy\\[all\\]' \"$GR_DIR/INSTALL.md\""
assert "INSTALL.md registers claw skill (graphify install --platform claw)" "grep -q 'graphify install --platform claw' \"$GR_DIR/INSTALL.md\""
assert "INSTALL.md installs the free AST hook (graphify hook install)" "grep -q 'graphify hook install' \"$GR_DIR/INSTALL.md\""
assert "INSTALL.md maps with client's own Ollama (--backend ollama)" "grep -q -- '--backend ollama' \"$GR_DIR/INSTALL.md\""
# OLLAMA_BASE_URL must carry the /v1 suffix (graphify passes it verbatim; a bare :11434 404s the semantic map).
assert "INSTALL.md pins OLLAMA_BASE_URL to the /v1 form" "grep -qE 'OLLAMA_BASE_URL=\"?http://localhost:11434/v1' \"$GR_DIR/INSTALL.md\""
assert "CORE_UPDATES.md pins OLLAMA_BASE_URL to the /v1 form" "grep -qE 'OLLAMA_BASE_URL=http://localhost:11434/v1' \"$GR_DIR/CORE_UPDATES.md\""
assert "SKILL.md pins OLLAMA_BASE_URL to the /v1 form" "grep -q 'localhost:11434/v1' \"$GR_DIR/SKILL.md\""
# No stale bare :11434 base URL may remain (would 404 the semantic map).
assert "no bare OLLAMA_BASE_URL=...:11434 without /v1 (INSTALL/CORE_UPDATES/SKILL)" "! grep -rEn 'OLLAMA_BASE_URL=\"?http://localhost:11434([^/]|\$)' \"$GR_DIR/INSTALL.md\" \"$GR_DIR/CORE_UPDATES.md\" \"$GR_DIR/SKILL.md\""
# Sovereignty: the bare-re-map violation rule must be documented (backend must be pinned to ollama).
assert "CORE_UPDATES.md documents the bare-re-map backend-pin violation rule" "grep -qiE 'bare .*re-map|BACKEND-PIN' \"$GR_DIR/CORE_UPDATES.md\""
assert "SKILL.md states semantic pass is owner-triggered / on-demand" "grep -qiE 'owner-triggered|on demand|on-demand' \"$GR_DIR/SKILL.md\""
assert "SKILL.md states AST rebuild is free + automatic" "grep -qiE 'free.*automatic|automatic.*free|FREE — no model' \"$GR_DIR/SKILL.md\""
assert "NEVER operator keys rule present (SKILL.md)" "grep -qiE 'NEVER.*operator|never the operator' \"$GR_DIR/SKILL.md\""
assert "NO-COMINGLING referenced (SKILL.md)" "grep -q 'NO-COMINGLING-RULE.md' \"$GR_DIR/SKILL.md\""
assert "wires /graphify for codebase/workforce questions (SKILL.md)" "grep -q '/graphify' \"$GR_DIR/SKILL.md\""
assert "no working artifacts shipped (.bak/.tmp/QC-READY.txt)" "[ \$(find \"$GR_DIR\" \\( -name '*.bak' -o -name '*.tmp' -o -name 'QC-READY.txt' \\) 2>/dev/null | wc -l | tr -d ' ') -eq 0 ]"

# Runtime (soft — present only after the client box runs INSTALL.md)
warn_only "graphify CLI installed on this box" "command -v graphify"

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 43 QC FAILED"; exit 1; } || { green "Skill 43 QC PASS"; exit 0; }
