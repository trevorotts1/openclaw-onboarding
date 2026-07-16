#!/usr/bin/env bash
# qc-lattice-pointer.sh — U89/GK-27 relationship lattice pointer + citation
# tripwire for Skill 38.
#
# WHAT THIS GATE STATICALLY ASSERTS (from the repo alone, no live box):
#   1. SKILL.md carries its one-line pointer to
#      docs/CONTENT-CONVERSATION-LATTICE.md (no content duplication — pointers
#      only, per the standing reference-links doctrine).
#   2. Every relationship-lattice edge this skill OWNS still cites real,
#      unchanged ground truth: the inbound-ownership statement ("Skill 38 OWNS
#      every inbound conversation those CTAs generate...") and the
#      build-path-ladder statements (caf-direct PRIMARY route + "NOT a hard
#      prereq") must still appear on the exact lines
#      docs/lattice-citations.json cites. If a cited line drifts (edited,
#      moved, or the file deleted), this gate FAILS — it never fabricates a
#      PASS. See docs/tools/check_lattice_citation.py for the shared checker
#      and docs/tools/test_check_lattice_citation.py for the fail-first proof.
#
# Exit codes: 0 = pointer + all owned citations pass; 1 = one or more fail.
#
# Usage: bash scripts/qc-lattice-pointer.sh [--skill-dir DIR]

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
CHECKER="$REPO_ROOT/docs/tools/check_lattice_citation.py"

echo ""
echo "═══ Skill 38 — Relationship lattice pointer + citation tripwire (GK-27) ═══"
echo ""

if [ ! -f "$CHECKER" ]; then
  echo "  ✗ FAIL — checker not found at $CHECKER"
  exit 1
fi

python3 "$CHECKER" --repo-root "$REPO_ROOT" --skill 38-conversational-ai-system
RC=$?

echo ""
if [ "$RC" -eq 0 ]; then
  echo "Skill 38 lattice pointer + citation tripwire PASS"
else
  echo "Skill 38 lattice pointer + citation tripwire FAILED"
fi
exit "$RC"
