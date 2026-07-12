#!/usr/bin/env bash
# tests/unit/guard-agent-browser-managed-scan-roots.test.sh — AUD-20 / FLEET-FIX
# Area 2 / B.2 negative-fixture proof, EXTENDED by P3-08 (Skill 44 scan root).
#
# Before AUD-20, scripts/guard-agent-browser-managed.sh's MANAGED-ONLY (1) and
# HEADLESS-ONLY (5) checks only scanned 06-ghl-install-pages/ — an unmanaged
# `agent-browser ... open|eval|...` call planted in 41-build-with-ai-playbook/
# or 03-agent-browser/ passed the guard SILENTLY (guard exit 0). AUD-20 widened
# the scan to those two roots; this test proves the guard catches it in BOTH.
#
# P3-08 (2026-07-11) widens the SAME guard INCLUSIVELY to a fourth root —
# 44-convert-and-flow-operator/ — BEFORE any Tier-4 agent-browser workflow-build
# code lands there, so the guard bites the FIRST unmanaged spawn, not the second
# incident (Skill 44's SKILL.md/INSTRUCTIONS.md promise a Tier-4 agent-browser
# backstop that had zero implementation and zero CI protection — the exact 22-
# orphan/357MB shape). The 06/41/03 coverage is NEVER removed or narrowed — the
# fourth root is ADDED alongside them (coordinates with P3-04, which widens the
# same guard to further skill dirs; both widenings are inclusive supersets).
# This test now proves the guard bites an unmanaged spawn planted in ALL THREE
# newly-scanned roots (41-*, 03-*, AND 44-*).
#
# Runs the REAL guard script against a MINIMAL synthetic --repo-root (not a
# full `cp -a` of the whole monorepo) containing just what section (0)-(4)
# need to pass (the gateway files + sentinel docs) plus the two new scan
# roots -- so each guard invocation is fast and this test is hermetic /
# independent of unrelated drift elsewhere in the real 06-ghl-install-pages/
# tree (which carries ~90 real .py files the full guard also scans, and
# which this test does not need to touch to prove the AUD-20 fix).
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/guard-agent-browser-managed.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== guard-agent-browser-managed-scan-roots.test.sh (AUD-20) ==="
[[ -f "$GUARD" ]] || { echo "FAIL: guard not found: $GUARD"; exit 1; }

TMP_TREE="$(mktemp -d)"
trap 'rm -rf "$TMP_TREE"' EXIT

# ── Build the minimal synthetic tree the guard's sections (0)-(4) require ────
mkdir -p \
  "$TMP_TREE/06-ghl-install-pages/tools" \
  "$TMP_TREE/scripts" \
  "$TMP_TREE/41-build-with-ai-playbook/scripts" \
  "$TMP_TREE/03-agent-browser" \
  "$TMP_TREE/44-convert-and-flow-operator/tools"

# Section (0): gateway files must exist.
# Section (2): browser_manager.sh must carry all 5 teardown/lock/breaker markers.
cat > "$TMP_TREE/06-ghl-install-pages/tools/browser_manager.sh" <<'EOF'
#!/usr/bin/env bash
# Minimal stub satisfying guard section (2) GATEWAY INTEGRITY verbatim markers.
_bm_teardown() { :; }
trap _bm_teardown EXIT
bm_lock() { mkdir "$LOCKDIR/ab.lock.d"; }
bm_close() { agent-browser close --session "$1"; }
bm_state_clear() { agent-browser state clear; }
bm_breaker_check() { :; }
AB() { agent-browser --session "$1" "${@:2}"; }
EOF
: > "$TMP_TREE/06-ghl-install-pages/tools/browser_manager.py"
cat > "$TMP_TREE/scripts/agent-browser-reaper.sh" <<'EOF'
#!/usr/bin/env bash
: # minimal stub
EOF

# Section (4): the doctrine sentinel must appear verbatim in all 3 required docs.
SENTINEL='SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop'
for doc in SKILL.md ghl-browser-builder-full.md CORE_UPDATES.md; do
  printf '%s\n' "$SENTINEL" > "$TMP_TREE/06-ghl-install-pages/$doc"
done

# ── (A) Baseline: the minimal synthetic tree PASSES clean ────────────────────
echo ""
echo "--- (A) baseline: minimal tree (incl. empty 41-*/03-*/44-* roots) passes ---"
A_OUT="$(bash "$GUARD" --repo-root "$TMP_TREE" 2>&1)"
A_EXIT=$?
if [[ "$A_EXIT" -eq 0 ]]; then
  pass "(A) guard PASSES on the clean synthetic tree (41-*/03-* scanned, zero false positives)"
else
  fail "(A) guard should PASS on the clean tree -- broadening introduced a false positive. Output: $(printf '%s' "$A_OUT" | tail -15)"
fi

# ── (B) Plant an unmanaged bare agent-browser call in BOTH new roots at once ─
# One combined guard run for both roots (keeps this test to 3 total guard
# invocations instead of 5) -- still proves each root individually via its
# own named hit in the output.
echo ""
echo "--- (B) planted unmanaged spawn in 41-* AND 03-* AND 44-* -> guard MUST FAIL on all three ---"
FIXTURE_41="$TMP_TREE/41-build-with-ai-playbook/scripts/zz-planted-unmanaged-probe.sh"
cat > "$FIXTURE_41" <<'EOF'
#!/usr/bin/env bash
# Planted negative fixture (AUD-20 test only) -- a raw, unmanaged agent-browser
# spawn that does NOT route through 06-ghl-install-pages/tools/browser_manager.sh.
agent-browser --session zz-planted-test open https://example.com
EOF
FIXTURE_03="$TMP_TREE/03-agent-browser/zz-planted-unmanaged-probe.sh"
cat > "$FIXTURE_03" <<'EOF'
#!/usr/bin/env bash
# Planted negative fixture (AUD-20 test only) -- same unmanaged spawn shape,
# planted in the OTHER newly-scanned root.
agent-browser snapshot -i
EOF
# P3-08 fixture: the exact QC break-it probe -- a Tier-4 workflow-build callsite
# that spawns agent-browser directly in 44-convert-and-flow-operator/tools/
# instead of routing through Skill 6's browser_manager.sh singleton gateway.
# This is precisely the class of unguarded first-implementation the widening
# exists to catch. Python argv-list spawn form (the exact shape the AST pass in
# scan_python_argv_spawn is built to bite).
FIXTURE_44="$TMP_TREE/44-convert-and-flow-operator/tools/zz-planted-tier4-workflow-builder.py"
cat > "$FIXTURE_44" <<'EOF'
#!/usr/bin/env python3
# Planted negative fixture (P3-08 test only) -- a raw, unmanaged agent-browser
# spawn for a Tier-4 Automations-UI workflow build that bypasses Skill 6's
# browser_manager.sh singleton gateway. MUST be caught by the widened guard.
import subprocess
subprocess.run(["agent-browser", "--session", "caf-tier4-build", "open",
                "https://app.gohighlevel.com/automations"])
EOF

B_OUT="$(bash "$GUARD" --repo-root "$TMP_TREE" 2>&1)"
B_EXIT=$?
if [[ "$B_EXIT" -ne 0 ]]; then
  pass "(B) guard FAILS (exit $B_EXIT) with all three fixtures planted"
else
  fail "(B) guard did NOT bite with unmanaged spawns planted in 41-*/03-*/44-* (exit 0 -- the guard is still blind to at least one root)"
fi
if printf '%s' "$B_OUT" | grep -q "41-build-with-ai-playbook/scripts/zz-planted-unmanaged-probe.sh"; then
  pass "(B) guard's failure output names the 41-build-with-ai-playbook/ planted file"
else
  fail "(B) guard should name the 41-* planted file (got: $(printf '%s' "$B_OUT" | grep -i 'fail\|zz-planted' | head -5 | tr '\n' ';'))"
fi
if printf '%s' "$B_OUT" | grep -q "03-agent-browser/zz-planted-unmanaged-probe.sh"; then
  pass "(B) guard's failure output names the 03-agent-browser/ planted file"
else
  fail "(B) guard should name the 03-* planted file (got: $(printf '%s' "$B_OUT" | grep -i 'fail\|zz-planted' | head -5 | tr '\n' ';'))"
fi
if printf '%s' "$B_OUT" | grep -q "44-convert-and-flow-operator/tools/zz-planted-tier4-workflow-builder.py"; then
  pass "(B) guard's failure output names the 44-convert-and-flow-operator/ planted file (P3-08)"
else
  fail "(B/P3-08) guard should name the 44-* planted file -- the guard is still BLIND to Skill 44 (got: $(printf '%s' "$B_OUT" | grep -i 'fail\|zz-planted' | head -5 | tr '\n' ';'))"
fi

rm -f "$FIXTURE_41" "$FIXTURE_03" "$FIXTURE_44"

# ── (C) Clean tree passes again after every fixture is removed ───────────────
echo ""
echo "--- (C) tree passes again once all planted fixtures are removed ---"
C_OUT="$(bash "$GUARD" --repo-root "$TMP_TREE" 2>&1)"
C_EXIT=$?
if [[ "$C_EXIT" -eq 0 ]]; then
  pass "(C) guard PASSES again after all fixtures removed (41-*/03-*/44-* fixtures left no residue)"
else
  fail "(C) guard should PASS once fixtures are removed. Output: $(printf '%s' "$C_OUT" | tail -15)"
fi

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi
