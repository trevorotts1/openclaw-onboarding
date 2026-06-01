#!/usr/bin/env bash
# qc-no-fabrication.sh -- Skill 41. UNIVERSAL gate: the no-fabrication floor and honest-gap path
# must be documented in the runtime guide and codified as a memory rule. Absence of a GHL feature
# must route to an honest gap, never an invented record.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTRUCTIONS="$SKILL_DIR/INSTRUCTIONS.md"
CORE="$SKILL_DIR/CORE_UPDATES.md"
echo "[skill 41 QC] no-fabrication: checking..."
PASS=0; TOTAL=3
if grep -qiE 'never fabricat|do not fabricat|non.?fabricat|no.?fabricat' "$INSTRUCTIONS" 2>/dev/null; then
  echo "  OK instructions: no-fabrication rule present"; PASS=$((PASS + 1))
else echo "  FAIL instructions: no-fabrication rule missing"; fi
if grep -qi 'honest gap' "$INSTRUCTIONS" 2>/dev/null; then
  echo "  OK instructions: honest-gap path present"; PASS=$((PASS + 1))
else echo "  FAIL instructions: honest-gap path missing"; fi
if grep -qiE 'no.?fabricat|never invent' "$CORE" 2>/dev/null; then
  echo "  OK core: no-fabrication memory rule present"; PASS=$((PASS + 1))
else echo "  FAIL core: no-fabrication memory rule missing"; fi
if [[ $PASS -eq $TOTAL ]]; then echo "[skill 41 QC] PASS no-fabrication"; exit 0; else echo "[skill 41 QC] FAIL no-fabrication ($PASS/$TOTAL)"; exit 1; fi
