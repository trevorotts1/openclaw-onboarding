#!/usr/bin/env bash
# Skill 43 — verify-graphify-install.sh
# Lightweight structural/install check for graphify.
# Exits 1 on any hard failure, 0 when the install is in place.
# Soft checks (graph mapped, hook installed) WARN but do not fail, since the
# semantic map is owner-triggered and the target folder may not be a git repo yet.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

FAIL=0
ok(){   printf "  [OK]   %s\n" "$1"; }
warn(){ printf "  [WARN] %s\n" "$1"; }
bad(){  printf "  [FAIL] %s\n" "$1"; FAIL=$((FAIL+1)); }

# Surface common tool bins for non-login shells.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"

echo ""
echo "Graphify Knowledge Graph (Skill 43) — install verification"
echo "Skill dir: $SKILL_DIR"
echo ""

# 1. Skill folder files present
for f in SKILL.md INSTALL.md INSTRUCTIONS.md CORE_UPDATES.md CHANGELOG.md skill-version.txt references/GRAPHIFY-COMMANDS.md; do
  [ -f "$SKILL_DIR/$f" ] && ok "skill file: $f" || bad "skill file MISSING: $f"
done

# 2. graphify CLI installed
if command -v graphify >/dev/null 2>&1; then
  ok "graphify CLI present ($(command -v graphify))"
else
  bad "graphify CLI not found — run: uv tool install \"graphifyy[all]\""
fi

# 3. OpenClaw claw skill registered (best-effort detection)
CLAW_SKILL=""
for cand in "$HOME/.openclaw/skills/graphify" "$HOME/.config/openclaw/skills/graphify" "$HOME/.openclaw/skills/graphify.skill"; do
  [ -e "$cand" ] && CLAW_SKILL="$cand" && break
done
if [ -n "$CLAW_SKILL" ]; then
  ok "OpenClaw graphify skill registered ($CLAW_SKILL)"
else
  warn "Could not auto-detect the claw skill — confirm 'graphify install --platform claw' ran"
fi

# 4. Optional: a mapped graph for a target folder passed as $1
TARGET="${1:-}"
if [ -n "$TARGET" ]; then
  if [ -f "$TARGET/graphify-out/graph.json" ]; then
    ok "graph mapped: $TARGET/graphify-out/graph.json"
  else
    warn "no graphify-out/graph.json in $TARGET (semantic map is owner-triggered — may be expected)"
  fi
  if [ -d "$TARGET/.git/hooks" ] && grep -rqi graphify "$TARGET/.git/hooks" 2>/dev/null; then
    ok "AST auto-rebuild hook installed in $TARGET"
  else
    warn "no graphify git hook detected in $TARGET (run 'graphify hook install' in the mapped repo)"
  fi
else
  warn "no target folder passed — skipping graph + hook checks (pass the mapped folder as arg 1 to check)"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "PASS — graphify skill files present and CLI installed. (WARNs are owner-triggered/optional steps.)"
  exit 0
else
  echo "FAIL — $FAIL hard problem(s) found."
  exit 1
fi
