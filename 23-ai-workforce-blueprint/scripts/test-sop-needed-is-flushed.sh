#!/usr/bin/env bash
# test-sop-needed-is-flushed.sh — BU-108 acceptance test.
#
# Phase 1: a roles file naming one role in no library, run through
# create_role_workspaces.py --roles-json; SOP-NEEDED.json must exist with
# open_count == 1. Phase 2: an empty role folder under a second department,
# run post-build-role-workspaces.py; open_count must become 2.
#
# The company lives where post-build resolves it:
# $HOME/.openclaw/workspace/zero-human-company/acme (OPENCLAW_PLATFORM=mac,
# empty HOME). Phase 1 runs there directly so both phases share one root.
# Exit non-zero on any mismatch.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T="$(mktemp -d -p "${TMPDIR:-/tmp}")"
trap 'rm -rf "$T"' EXIT
export HOME="$T/home" OPENCLAW_PLATFORM=mac MASTER_FILES_DIR="$T/mf" \
  WORKFORCE_BUILD_STATE_FILE="$T/state.json"
Z="$T/home/.openclaw/workspace/zero-human-company"
mkdir -p "$T/home" "$Z/acme/departments/widgets" "$T/ws"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "[PASS] $1"; }
fail() { FAIL=$((FAIL+1)); echo "[FAIL] $1"; }

echo "--- phase 1: create_role_workspaces.py --roles-json ---"
python3 - "$T" >"$T/roles.json" <<'PYEOF'
import json, sys
json.dump([{"name": "Quantum Widget Wrangler", "type": "full-time-permanent",
            "number": 1, "description": "QC probe, no library match"}],
          open(sys.argv[1] + "/roles.json", "w"))
PYEOF
if python3 -B "$SCRIPT_DIR/create_role_workspaces.py" \
    --dept-path "$Z/acme/departments/widgets" --roles-json "$T/roles.json" \
    --workspace-root "$T/ws" >"$T/run1.log" 2>"$T/run1.err"; then
  pass "create exit 0"
else
  fail "create exit $?"
fi
OPEN1="$(python3 -B -c "import json; print(json.load(open('$Z/acme/SOP-NEEDED.json'))['open_count'])" 2>/dev/null || echo MISSING)"
if [ "$OPEN1" = "1" ]; then
  pass "SOP-NEEDED.json exists with open_count == 1"
else
  fail "phase 1 open_count is '$OPEN1', want 1"
fi

echo "--- phase 2: post-build-role-workspaces.py ---"
mkdir -p "$Z/acme/departments/gadgets/01-empty-role"
# A complete master-orchestrator folder: post-build then augments nothing for
# the CEO (no new record), so phase 2 adds exactly the one empty-role record.
mkdir -p "$Z/acme/master-orchestrator/SOP"
for f in IDENTITY.md SOUL.md MEMORY.md HEARTBEAT.md how-to.md; do
  echo "complete" > "$Z/acme/master-orchestrator/$f"
done
echo "index" > "$Z/acme/master-orchestrator/SOP/00-INDEX.md"
if OPENCLAW_COMPANY_SLUG=acme python3 -B "$SCRIPT_DIR/post-build-role-workspaces.py" \
    --company-slug acme >"$T/run2.log" 2>"$T/run2.err"; then
  pass "post-build exit 0"
else
  fail "post-build exit $?"
fi
OPEN2="$(python3 -B -c "import json; print(json.load(open('$Z/acme/SOP-NEEDED.json'))['open_count'])" 2>/dev/null || echo MISSING)"
if [ "$OPEN2" = "2" ]; then
  pass "SOP-NEEDED.json exists with open_count == 2"
else
  fail "phase 2 open_count is '$OPEN2', want 2"
fi

echo "RESULTS: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
