#!/usr/bin/env bash
# Skill 01 — Teach Yourself Protocol (TYP) — Install QC
# TYP is the foundation: it governs how the agent stores knowledge (3-layer model).
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

echo ""
echo "═══ Skill 01 — Teach Yourself Protocol — Install QC ═══"
echo "  Platform: ${OPENCLAW_PLATFORM:-unknown}"
echo ""
echo "── Section A: TYP installed at canonical location ──"
assert "TYP folder present"   "[ -d \"$SKILLS_DIR_DEFAULT/01-teach-yourself-protocol\" ]"
assert "SKILL.md present"     "[ -f \"$SKILLS_DIR_DEFAULT/01-teach-yourself-protocol/SKILL.md\" ]"
assert "INSTALL.md present"   "[ -f \"$SKILLS_DIR_DEFAULT/01-teach-yourself-protocol/INSTALL.md\" ]"
assert "QC.md present"        "[ -f \"$SKILLS_DIR_DEFAULT/01-teach-yourself-protocol/QC.md\" ]"
assert "Full reference doc"   "[ -f \"$SKILLS_DIR_DEFAULT/01-teach-yourself-protocol/teach-yourself-protocol-full.md\" ]"
echo ""
echo "── Section B: 3-layer storage model wired ──"
warn_only "AGENTS.md references TYP" "grep -qiE 'teach.yourself.protocol|TYP' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
warn_only "Master-files folder full reference"  "find $HOME/Downloads ~/Downloads 2>/dev/null -maxdepth 4 -name 'teach-yourself-protocol-full.md' | head -1 | grep -q ."
warn_only "Core .md files exist (AGENTS / TOOLS / MEMORY)" "[ -f \"$WORKSPACE/AGENTS.md\" ] && [ -f \"$WORKSPACE/TOOLS.md\" ] && [ -f \"$WORKSPACE/MEMORY.md\" ]"
if grep -q 'CORE_REFERENCE_POLICY_V1' "$WORKSPACE/AGENTS.md" "$WORKSPACE/MEMORY.md" "$WORKSPACE/TOOLS.md" 2>/dev/null; then
  for spec in AGENTS.md:15000 MEMORY.md:8000 TOOLS.md:15000; do
    core_name="${spec%:*}"; core_limit="${spec#*:}"
    if python3 - "$WORKSPACE/$core_name" "$core_limit" <<'TYP_BUDGET_PY'
from pathlib import Path
import sys
try:
    size = len(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, UnicodeError) as exc:
    print(f"Cannot verify {Path(sys.argv[1]).name}: {exc}")
    raise SystemExit(1)
limit = int(sys.argv[2])
print(f"  {Path(sys.argv[1]).name}: {size} / {limit} characters")
raise SystemExit(0 if size <= limit else 1)
TYP_BUDGET_PY
    then
      green "  ✓ PASS — $core_name compact character budget"; PASS=$((PASS+1))
    else
      red "  ✗ FAIL — $core_name compact character budget"; FAIL=$((FAIL+1))
    fi
  done
else
  warn_only "AGENTS.md under 50KB (TYP lean-file rule)" "[ \$(stat -f %z \"$WORKSPACE/AGENTS.md\" 2>/dev/null || stat -c %s \"$WORKSPACE/AGENTS.md\" 2>/dev/null || echo 0) -lt 51200 ]"
fi
echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 01 QC FAILED"; exit 1; } || { green "Skill 01 QC PASS"; exit 0; }
