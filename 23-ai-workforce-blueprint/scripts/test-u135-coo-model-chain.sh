#!/usr/bin/env bash
# test-u135-coo-model-chain.sh — Verify COO/Pippen identity uses canonical model
# resolution chain, not a hardcoded model name (U135).
#
# Exit codes (fail-closed):
#   0 — PASS: no stale hardcoded model references remain
#   1 — FAIL: stale DEFAULT_MODEL_ASSIGNMENTS dict still present
#   2 — FAIL: stale model id found (minimax-m3, gpt-5.4)
#   3 — FAIL: dept-model-suitability.json missing operations entry
#   4 — FAIL: resolve_dept_agent_model missing
#   5 — FAIL: build-workforce.py does not compile

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BW="${SCRIPT_DIR}/build-workforce.py"
RED='\033[0;31m'
GRN='\033[0;32m'
NC='\033[0m'

fail() { echo -e "${RED}FAIL${NC}: $*"; exit "$1"; }
pass() { echo -e "${GRN}PASS${NC}: $*"; }

# CHECK 1: DEFAULT_MODEL_ASSIGNMENTS not defined as uncommented code
echo "--- CHECK 1: DEFAULT_MODEL_ASSIGNMENTS removed ---"
if grep -nE '^DEFAULT_MODEL_ASSIGNMENTS[[:space:]]*=' "$BW" 2>/dev/null; then
    fail 1 "DEFAULT_MODEL_ASSIGNMENTS still defined in $BW"
fi
pass "DEFAULT_MODEL_ASSIGNMENTS dict removed"

# CHECK 2: No stale model ids on uncommented lines
echo "--- CHECK 2: Stale model ids absent ---"
if grep -nE 'minimax-m3:cloud|openai-codex/gpt-5\.4' "$BW" 2>/dev/null | grep -vE '^[0-9]+:[[:space:]]*#'; then
    fail 2 "stale model id in uncommented code in $BW"
fi
pass "No stale hardcoded model ids found"

# CHECK 3: resolve_dept_agent_model present
echo "--- CHECK 3: Canonical resolution chain wired ---"
grep -q 'def resolve_dept_agent_model(' "$BW" 2>/dev/null || fail 4 "resolve_dept_agent_model() missing"
pass "resolve_dept_agent_model() present"

# CHECK 4: operations in dept-model-suitability.json
echo "--- CHECK 4: operations (COO) suitability mapped ---"
SUIT_FILE="${SCRIPT_DIR}/../../shared-utils/dept-model-suitability.json"
[ -f "$SUIT_FILE" ] || fail 3 "dept-model-suitability.json not found at $SUIT_FILE"
SUIT_TIER=$(python3 -c "
import json
with open('$SUIT_FILE') as f:
    d = json.load(f)
ops = d.get('departments', {}).get('operations')
print(ops.get('tier','NO_TIER') if ops else 'MISSING')
")
[ "$SUIT_TIER" != "MISSING" ] || fail 3 "operations missing from dept-model-suitability.json"
pass "operations (COO) department mapped to tier '$SUIT_TIER'"

# CHECK 5: build-workforce.py compiles
echo "--- CHECK 5: $BW compiles ---"
python3 -c "import py_compile; py_compile.compile('$BW', doraise=True)" || fail 5 "$(basename "$BW") does not compile"
pass "$(basename "$BW") compiles"

# CHECK 6: U135 marker present
echo "--- CHECK 6: U135 change marker ---"
grep -q 'U135' "$BW" 2>/dev/null || fail 6 "U135 marker missing from $BW"
pass "U135 canonical chain comment present"

echo ""
echo "==========================================="
echo "U135: All checks PASSED"
echo "COO/Pippen identity -> canonical resolution chain"
echo "==========================================="
