#!/usr/bin/env bash
# tests/unit/rr030-triage-selftest-failsonly.test.sh
# ---------------------------------------------------------------------------
# RR-030 — proves scripts/rr-triage.sh --self-test cannot hide failures:
#   1. BASELINE defect class: a failure raised INSIDE a fixture subshell used
#      to be lost (counter incremented in the subshell). On the repaired
#      script a forced fixture failure MUST make --self-test exit nonzero;
#   2. the fixture tree is addressed through the explicit OC_CONFIG_ROOT —
#      the self-test must run green with the real HOME untouched, and a
#      fixture that plants state must never leak into the operator tree;
#   3. the healthy self-test still exits 0.
# ---------------------------------------------------------------------------
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRIAGE="$REPO_ROOT/scripts/rr-triage.sh"
[ -f "$TRIAGE" ] || { echo "FATAL: $TRIAGE not found"; exit 2; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 3. healthy self-test green (assumption control) ------------------------
if bash "$TRIAGE" --self-test > "$WORK/healthy.log" 2>&1; then
  ok "healthy --self-test exits 0"
else
  bad "healthy --self-test rc=$? (fixture or checker regression)"
fi
grep -q "0 failure(s)" "$WORK/healthy.log" || bad "healthy run summary missing"

# --- 1. forced fixture failure must surface --------------------------------
sed 's/echo "  ✓ healthy config: streaming + toolSearch both CLEAN"/echo "  ✗ FORCED-FAIL (mutation)"; exit 9/' \
  "$TRIAGE" > "$WORK/triage-mut.sh"
if bash "$WORK/triage-mut.sh" --self-test > "$WORK/forced.log" 2>&1; then
  bad "forced fixture failure still exited 0 — the subshell swallow is back"
else
  ok "forced fixture failure -> --self-test nonzero"
fi
grep -q "FORCED-FAIL" "$WORK/forced.log" || bad "forced-fail line missing from output"
grep -qE "failure\(s\)" "$WORK/forced.log" && grep -qE "[1-9][0-9]* failure" "$WORK/forced.log" \
  && ok "failure counter visible in summary" || bad "summary did not count the forced failure"

# --- 2. explicit root: fixtures never touch the real HOME ------------------
# Run the healthy self-test with OC_CONFIG_ROOT pinned to the sandbox AND a
# HOME sentinel that would break real-box detection if any step leaked.
SENTINEL="$WORK/home-sentinel"; mkdir -p "$SENTINEL/.openclaw/agents/main"
printf '{"agents":{"list":[{"id":"main"}]}}' > "$SENTINEL/.openclaw/openclaw.json"
if HOME="$SENTINEL" OC_CONFIG_ROOT="$WORK/unused-root" bash "$TRIAGE" --self-test > "$WORK/root.log" 2>&1; then
  ok "self-test green with an explicit OC_CONFIG_ROOT and a sentinel HOME"
else
  bad "self-test failed under explicit-root mode (leak or regression)"
fi
if grep -q "home-sentinel" "$WORK/root.log"; then
  bad "fixture output referenced the sentinel HOME — a step leaked past OC_CONFIG_ROOT"
else
  ok "no fixture step read the sentinel HOME"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "[rr030-triage-selftest-failsonly] PASS ($PASS assertions)"
  exit 0
fi
echo "[rr030-triage-selftest-failsonly] FAIL ($FAIL of $((PASS+FAIL)) assertions failed)"
exit 1