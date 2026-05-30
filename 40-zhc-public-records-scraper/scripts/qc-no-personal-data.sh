#!/usr/bin/env bash
# qc-no-personal-data.sh — machine-enforce that the UNIVERSAL Skill 40 contains
# ZERO real personal / client identifiers anywhere in its source tree.
# Replace each with a generic placeholder. Exit 0 = clean; 1 = found.
# BASH only (grep core). This file is excluded from the scan.
#
# Usage: bash scripts/qc-no-personal-data.sh [--skill-dir DIR]

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SELF_NAME="$(basename "$0")"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,12p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Banned REAL identifiers (ERE alternation). Same roster as Skill 38's gate.
# NOTE: "Marico" uses a trailing word boundary so it catches the client
# "Marico"/"Marico Consulting" but NOT the public entity "Maricopa County".
BANNED='Trevor|Teresa|Keez|Christy|Corey|Angeleen|Beverly|Candace|Marico\b|Sir Jordan|Grants Boutique|Explore Growth|The Winning Formula Course|Winning Formula|thewinningformulacourse|growthriveprosper|blackceo|5252140759|trevelynotts|/Users/christy|/Users/blackceomacmini|/Users/client'

echo "=== qc-no-personal-data (Skill 40): UNIVERSAL-skill identifier gate ==="
echo "skill dir : $SKILL_DIR"
echo ""

HITS=0
TREE_HITS="$(grep -rinE "$BANNED" "$SKILL_DIR" --exclude-dir='.git' --exclude="$SELF_NAME" 2>/dev/null || true)"
if [ -n "$TREE_HITS" ]; then
  echo "Banned identifiers found in the skill tree:"
  printf '%s\n' "$TREE_HITS" | sed 's/^/  [HIT] /'
  HITS=$(printf '%s\n' "$TREE_HITS" | grep -c .)
fi

echo ""
if [ "$HITS" -eq 0 ]; then
  echo "RESULT: PASS — no real personal/client identifiers in Skill 40 (UNIVERSAL)."
  exit 0
else
  echo "RESULT: FAIL — $HITS banned-identifier occurrence(s). Replace each with a generic placeholder."
  exit 1
fi
