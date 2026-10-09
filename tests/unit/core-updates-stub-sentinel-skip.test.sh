#!/usr/bin/env bash
# tests/unit/core-updates-stub-sentinel-skip.test.sh
#
# W2 regression lock for the CORE_UPDATES skip-check / gate asymmetry.
#
# THE DEFECT: wire_core_updates()'s sentinel skip-check carried an extra leg
# reading the legacy 2026.x agent-dir stub ($WIRE_AGENT_DIR/AGENTS.md), while
# the verification gate (scripts/onboarding-state.sh:456-465 and
# lib-onboarding-state.sh oc_core_sentinel_present) reads ONLY the workspace
# core files. A stale stub sentinel short-circuited the merge forever while the
# gate kept reporting core-updates:sentinel-missing for 01/02/03/69/71/72.
#
# BOTH DIRECTIONS, on the REAL function extracted from update-skills.sh:
#   (A) stub sentinel present, workspace empty  -> payload MUST still merge
#       (the fix); pre-fix this returned 0 without merging.
#   (B) workspace sentinel present, stub empty  -> MUST skip (idempotency holds).
#
# Exit 0 = both directions hold. Exit 1 = regression.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

echo "=== core-updates-stub-sentinel-skip.test.sh ==="
echo ""

# Extract the REAL wire_core_updates() body by brace-matching (never by fixed
# line numbers — two other extractors in this repo use ranges and go stale).
FUNC_FILE="$T/wire_core_updates.sh"
python3 - "$REPO_ROOT/update-skills.sh" > "$FUNC_FILE" <<'PYEOF'
import sys
lines = open(sys.argv[1], encoding='utf-8').read().split('\n')
start = None
for i, l in enumerate(lines):
    if l.strip() == 'wire_core_updates() {':
        start = i
        break
if start is None:
    sys.exit('wire_core_updates() not found')
for j in range(start + 1, len(lines)):
    if lines[j] == '  }':
        print('\n'.join(lines[start:j + 1]))
        sys.exit(0)
sys.exit('closing brace not found')
PYEOF

if ! grep -q 'wire_core_updates() {' "$FUNC_FILE"; then
  fail "extractor: wire_core_updates() not extracted"
  echo "RESULTS: $PASS passed, $FAIL failed"
  exit 1
fi
pass "extractor: wire_core_updates() extracted from update-skills.sh"

# The defect leg must be GONE from the SKIP-CHECK specifically: between
# `local SENTINEL=` and its `return 0`, no read of $WIRE_AGENT_DIR. (The
# dual-write near the function's end legitimately still touches WIRE_AGENT_DIR.)
if python3 - "$FUNC_FILE" <<'PYEOF'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'local SENTINEL=.*?\n\s*fi\n', src, re.S)
if not m:
    sys.exit(2)
sys.exit(1 if 'WIRE_AGENT_DIR' in m.group(0) else 0)
PYEOF
then
  pass "skip-check no longer trusts the agent-dir stub sentinel"
else
  rc=$?
  [ "$rc" = 2 ] && fail "skip-check block not located in extracted function" \
               || fail "skip-check still reads the agent-dir stub (\$WIRE_AGENT_DIR) for the sentinel"
fi

# ── Fixture: a real skill with a mergeable CORE_UPDATES payload ─────────────
SKILL_DIR="$T/skills"
mkdir -p "$SKILL_DIR/01-teach-yourself-protocol"
cat > "$SKILL_DIR/01-teach-yourself-protocol/CORE_UPDATES.md" <<'CUEOF'
# 01 — teach yourself protocol

## AGENTS.md - UPDATE REQUIRED

TEACH YOURSELF PROTOCOL sentinel-body-marker
CUEOF

run_case() { # $1 = stub-sentinel 0/1, $2 = workspace-sentinel 0/1
  local stub="$1" wsp="$2" box="$T/box_${1}_${2}"
  mkdir -p "$box/home/.openclaw/agents/main" "$box/ws"
  printf '' > "$box/home/.openclaw/agents/main/AGENTS.md"
  [ "$stub" = 1 ] && printf '<!-- skill:01-teach-yourself-protocol:core-update-applied -->\n' \
    >> "$box/home/.openclaw/agents/main/AGENTS.md"
  for f in AGENTS TOOLS MEMORY SOUL IDENTITY USER; do
    printf '' > "$box/ws/$f.md"
  done
  [ "$wsp" = 1 ] && printf '<!-- skill:01-teach-yourself-protocol:core-update-applied -->\n' \
    >> "$box/ws/AGENTS.md"

  HOME="$box/home" SANDBOX="$box" SKILLS_DIR="$SKILL_DIR" \
  CU_MASTER_FILES_DIR="$T/master" bash -c '
    set -u
    oc_resolve_workspace_announced() { OC_WS_RESOLVED="$SANDBOX/ws"; return 0; }
    source "$1"
    WIRE_WORKSPACE_DIR="$SANDBOX/ws"
    WIRE_AGENT_DIR="$HOME/.openclaw/agents/main"
    wire_core_updates 01-teach-yourself-protocol
    echo "FUNC_RC=$?"
  ' _ "$FUNC_FILE" > "$box/out.txt" 2>&1
}

# (A) stale stub sentinel only -> the payload MUST merge into the workspace.
run_case 1 0
if grep -q 'Wired CORE_UPDATES.md' "$T/box_1_0/out.txt" && \
   grep -q 'TEACH YOURSELF PROTOCOL sentinel-body-marker' "$T/box_1_0/ws/AGENTS.md"; then
  pass "(A) stale agent-dir stub sentinel no longer blocks the workspace merge"
else
  fail "(A) stub sentinel still blocked the merge (payload absent from workspace AGENTS.md)"
  sed 's/^/    /' "$T/box_1_0/out.txt"
fi
if grep -qF '<!-- skill:01-teach-yourself-protocol:core-update-applied -->' "$T/box_1_0/ws/AGENTS.md"; then
  pass "(A) workspace sentinel landed (the gate's own read-path is now satisfied)"
else
  fail "(A) workspace sentinel missing after merge"
fi

# (B) workspace sentinel present -> merge MUST be skipped (idempotent).
run_case 0 1
if grep -q 'Wired CORE_UPDATES.md' "$T/box_0_1/out.txt"; then
  fail "(B) workspace sentinel no longer short-circuits the re-merge"
  sed 's/^/    /' "$T/box_0_1/out.txt"
else
  pass "(B) workspace sentinel still short-circuits the re-merge (idempotency holds)"
fi
if grep -q 'sentinel-body-marker' "$T/box_0_1/ws/AGENTS.md"; then
  fail "(B) payload was re-merged despite the workspace sentinel"
else
  pass "(B) payload not re-merged"
fi

echo ""
echo "RESULTS: $PASS passed, $FAIL failed"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
