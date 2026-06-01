#!/usr/bin/env bash
# qc-catalog-usecases.sh -- Skill 41. Asserts the trigger and action catalogs carry per-item use cases,
# the conditions reference covers If/Else depth, and the trigger-filters protocol exists.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TRIG="$SKILL_DIR/references/ghl-triggers-catalog.md"
ACT="$SKILL_DIR/references/ghl-actions-catalog.md"
COND="$SKILL_DIR/references/ghl-conditions-reference.md"
TFP="$SKILL_DIR/protocols/trigger-filters-protocol.md"
echo "[skill 41 QC] catalog-usecases: checking..."
PASS=0; TOTAL=5
TUC=$(grep -c 'Use when:' "$TRIG" 2>/dev/null || echo 0)
AUC=$(grep -c 'Use when:' "$ACT" 2>/dev/null || echo 0)
[ "$TUC" -ge 40 ] && { echo "  OK triggers carry use cases ($TUC)"; PASS=$((PASS+1)); } || echo "  FAIL triggers use cases too few ($TUC)"
[ "$AUC" -ge 30 ] && { echo "  OK actions carry use cases ($AUC)"; PASS=$((PASS+1)); } || echo "  FAIL actions use cases too few ($AUC)"
if grep -q 'Add Branch' "$COND" 2>/dev/null && grep -q 'None' "$COND" 2>/dev/null && grep -qE 'AND|OR' "$COND" 2>/dev/null; then echo "  OK if/else depth present"; PASS=$((PASS+1)); else echo "  FAIL if/else depth missing"; fi
if grep -qi 'Add filters' "$TFP" 2>/dev/null && grep -qiE 'Any of|None of' "$TFP" 2>/dev/null; then echo "  OK trigger-filters protocol present"; PASS=$((PASS+1)); else echo "  FAIL trigger-filters protocol missing"; fi
if grep -qi 'trigger filters' "$SKILL_DIR/protocols/build-with-ai-protocol.md" 2>/dev/null || grep -qi 'trigger-filters-protocol' "$SKILL_DIR/protocols/build-with-ai-protocol.md" 2>/dev/null; then echo "  OK build protocol references trigger filters"; PASS=$((PASS+1)); else echo "  FAIL build protocol does not reference trigger filters"; fi
if [ "$PASS" -eq "$TOTAL" ]; then echo "[skill 41 QC] PASS catalog-usecases"; exit 0; else echo "[skill 41 QC] FAIL catalog-usecases ($PASS/$TOTAL)"; exit 1; fi
