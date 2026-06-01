#!/usr/bin/env bash
# qc-dependency-order.sh -- Skill 41. Asserts dependency creation precedes prompt generation.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROTOCOL="$SKILL_DIR/protocols/build-with-ai-protocol.md"
INSTRUCTIONS="$SKILL_DIR/INSTRUCTIONS.md"
echo "[skill 41 QC] dependency-order: checking..."
PASS=0; TOTAL=2
if grep -q "Dependency creation" "$PROTOCOL" 2>/dev/null && grep -q "Prompt generation" "$PROTOCOL" 2>/dev/null; then
  DEP_LINE="$(grep -n "Dependency creation" "$PROTOCOL" | head -1 | cut -d: -f1)"
  PROMPT_LINE="$(grep -n "Prompt generation" "$PROTOCOL" | head -1 | cut -d: -f1)"
  if [[ -n "$DEP_LINE" && -n "$PROMPT_LINE" && "$DEP_LINE" -lt "$PROMPT_LINE" ]]; then
    echo "  OK protocol: dependency creation precedes prompt generation"; PASS=$((PASS + 1))
  else
    echo "  FAIL protocol: dependency creation does not precede prompt generation"
  fi
else
  echo "  FAIL protocol: missing dependency-creation or prompt-generation section"
fi
if grep -qiE 'must exist FIRST|dependency.*first' "$INSTRUCTIONS" 2>/dev/null && grep -qiE 'BEFORE generating|create.*before' "$INSTRUCTIONS" 2>/dev/null; then
  echo "  OK instructions: dependency-first rule documented"; PASS=$((PASS + 1))
else
  echo "  FAIL instructions: dependency-first rule not documented"
fi
if [[ $PASS -eq $TOTAL ]]; then echo "[skill 41 QC] PASS dependency-order"; exit 0; else echo "[skill 41 QC] FAIL dependency-order ($PASS/$TOTAL)"; exit 1; fi
