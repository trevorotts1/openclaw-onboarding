#!/usr/bin/env bash
# qc-zhc-tag-prefix.sh -- Skill 41. Asserts agent-created tags use ZHC- and custom fields use ZHC_,
# codified in the dependency protocol and the core-file updates.
set -uo pipefail
SKILL_DIR=""
while [[ $# -gt 0 ]]; do case "$1" in --skill-dir) SKILL_DIR="${2:-}"; shift 2;; *) shift;; esac; done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$SKILL_DIR" ]] && SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEP="$SKILL_DIR/protocols/dependency-creation-protocol.md"
CORE="$SKILL_DIR/CORE_UPDATES.md"
echo "[skill 41 QC] zhc-tag-prefix: checking..."
PASS=0; TOTAL=4
grep -q 'ZHC-' "$DEP" 2>/dev/null && { echo "  OK dep protocol: ZHC- tag prefix"; PASS=$((PASS+1)); } || echo "  FAIL dep protocol: ZHC- tag prefix missing"
grep -q 'ZHC_' "$DEP" 2>/dev/null && { echo "  OK dep protocol: ZHC_ field prefix"; PASS=$((PASS+1)); } || echo "  FAIL dep protocol: ZHC_ field prefix missing"
grep -q 'ZHC-' "$CORE" 2>/dev/null && { echo "  OK core: ZHC- tag prefix"; PASS=$((PASS+1)); } || echo "  FAIL core: ZHC- tag prefix missing"
grep -q 'ZHC_' "$CORE" 2>/dev/null && { echo "  OK core: ZHC_ field prefix"; PASS=$((PASS+1)); } || echo "  FAIL core: ZHC_ field prefix missing"
if [[ $PASS -eq $TOTAL ]]; then echo "[skill 41 QC] PASS zhc-tag-prefix"; exit 0; else echo "[skill 41 QC] FAIL zhc-tag-prefix ($PASS/$TOTAL)"; exit 1; fi
