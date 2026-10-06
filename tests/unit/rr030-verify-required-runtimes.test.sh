#!/usr/bin/env bash
# tests/unit/rr030-verify-required-runtimes.test.sh
# ---------------------------------------------------------------------------
# RR-030 — proves the department battery (rescue-rangers/scripts/verify.sh)
# enforces REQUIRED runtimes and REQUIRED cases:
#   1. node ABSENT from PATH -> the battery FAILS (baseline shipped
#      "ALL OFFLINE DRILLS PASS" with node gone — the defect);
#   2. the node-present run passes and prints the gate taxonomy;
#   3. the no-node run never prints "ALL OFFLINE DRILLS PASS".
# node is removed by giving verify.sh a PATH with only python3-visible tools:
# we build a sandbox bin dir containing python3 (symlink) and coreutils shims
# the battery needs, with NO node.
# ---------------------------------------------------------------------------
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERIFY="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/verify.sh"
[ -f "$VERIFY" ] || { echo "FATAL: $VERIFY not found"; exit 2; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Sandbox PATH: python3 + the shell tools verify.sh uses; NO node.
SB="$WORK/bin"; mkdir -p "$SB"
for t in python3 bash sh mkdir cp sed printf env grep seq kill rm chmod cat dirname basename mktemp; do
  src="$(command -v "$t" 2>/dev/null)" && ln -s "$src" "$SB/$t"
done
# /usr/bin/env is special on macOS (a binary, not a script) — symlink it too.
ln -s /usr/bin/env "$SB/env" 2>/dev/null

OUT_NO_NODE="$WORK/no-node.log"
PATH="$SB:/usr/bin:/bin" bash "$VERIFY" > "$OUT_NO_NODE" 2>&1
rc_no_node=$?

if grep -q "node not on PATH" "$OUT_NO_NODE" && [ "$rc_no_node" -ne 0 ]; then
  ok "node ABSENT -> battery FAILED (rc=$rc_no_node, reason printed)"
else
  bad "node-absent run: rc=$rc_no_node, node-missing reason printed: $(grep -c 'node not on PATH' "$OUT_NO_NODE")"
fi
if grep -q "ALL GATES GREEN\|ALL OFFLINE DRILLS PASS" "$OUT_NO_NODE"; then
  bad "node-absent run still printed an ALL-GREEN verdict (the RR-030 defect)"
else
  ok "node-absent run never prints an ALL-GREEN verdict"
fi

# Control: full PATH run is green (proves the sandbox PATH was the only delta).
OUT_FULL="$WORK/full.log"
bash "$VERIFY" > "$OUT_FULL" 2>&1
rc_full=$?
if [ "$rc_full" -eq 0 ] && grep -q "UNIT=1" "$OUT_FULL"; then
  ok "control: full run green with gate taxonomy (rc=0)"
else
  bad "control run failed (rc=$rc_full) — sandbox delta is not the only difference"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "[rr030-verify-required-runtimes] PASS ($PASS assertions)"
  exit 0
fi
echo "[rr030-verify-required-runtimes] FAIL ($FAIL of $((PASS+FAIL)) assertions failed)"
exit 1