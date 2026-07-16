#!/usr/bin/env bash
# tests/unit/guard-agent-browser-managed-backstop-conformance-exempt.test.sh
# ci-guard-red fix (2026-07-16).
#
# THE DEFECT: scripts/guard-agent-browser-managed.sh's MANAGED-ONLY check (1)
# auto-discovers EVERY NN-*/ skill directory as a scan root (AUD-25), with
# only browser_manager.sh/.py + the reaper exempt by exact path. GK-28/U90
# (commit 2057aefd) landed 03-agent-browser/scripts/lib-backstop-
# conformance.sh — Skill 3's OWN consumer conformance battery, which by
# design calls the raw `agent-browser` CLI directly (it PROVES the CLI's own
# contract that browser_manager.sh and Skill 44's Tier-4 fallback both
# assume; routing it through the Skill-6 gateway would invert the dependency
# and defeat the file's purpose). That file was never added to the guard's
# EXEMPT set, so every real (non-CI) run of the guard failed on origin/main
# with 4 violations at lines 94/105/116/128 — the "agent-browser lifecycle
# guard" GitHub Actions job was RED on every push.
#
# THE FIX: BACKSTOP_CONFORMANCE_SH is now in the guard's EXEMPT set, by EXACT
# absolute path (never a directory-wide carve-out for 03-agent-browser/).
#
# THIS TEST proves, on a minimal hermetic synthetic tree (same style as
# guard-agent-browser-managed-scan-roots.test.sh):
#   (A) a raw agent-browser call at the EXACT exempted path
#       (03-agent-browser/scripts/lib-backstop-conformance.sh) does NOT fail
#       the guard.
#   (B) the SAME raw call planted in a SIBLING file under 03-agent-browser/
#       (proving the exemption is narrow, not a directory-wide bypass) DOES
#       fail the guard, and the guard names that sibling file specifically —
#       never the exempted one.
#   (C) the tree passes again once the sibling fixture is removed.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/guard-agent-browser-managed.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== guard-agent-browser-managed-backstop-conformance-exempt.test.sh (ci-guard-red fix) ==="
[[ -f "$GUARD" ]] || { echo "FAIL: guard not found: $GUARD"; exit 1; }

TMP_TREE="$(mktemp -d)"
trap 'rm -rf "$TMP_TREE"' EXIT

# ── Build the minimal synthetic tree the guard's sections (0)-(4) require ────
mkdir -p \
  "$TMP_TREE/06-ghl-install-pages/tools" \
  "$TMP_TREE/scripts" \
  "$TMP_TREE/03-agent-browser/scripts"

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
SENTINEL='SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown, reaper backstop'
for doc in SKILL.md ghl-browser-builder-full.md CORE_UPDATES.md; do
  printf '%s\n' "$SENTINEL" > "$TMP_TREE/06-ghl-install-pages/$doc"
done

# ── (A) the EXEMPTED file itself: raw agent-browser calls at the EXACT
# real-world path must NOT fail the guard ─────────────────────────────────────
echo ""
echo "--- (A) raw agent-browser calls inside the exempted lib-backstop-conformance.sh path do NOT fail the guard ---"
cat > "$TMP_TREE/03-agent-browser/scripts/lib-backstop-conformance.sh" <<'EOF'
#!/usr/bin/env bash
# Mirrors the real file's leg 1/4 shape (raw CLI calls, by design).
run_conformance_battery() {
  agent-browser --headed false open --session "$1" "$2" >/dev/null 2>&1
  agent-browser --headed false snapshot --session "$1" -i >/dev/null 2>&1
  agent-browser --headed false fill --session "$1" "@e2" "value" >/dev/null 2>&1
}
EOF
A_OUT="$(bash "$GUARD" --repo-root "$TMP_TREE" 2>&1)"
A_EXIT=$?
if [[ "$A_EXIT" -eq 0 ]]; then
  pass "(A) guard PASSES with raw calls only inside the exempted lib-backstop-conformance.sh"
else
  fail "(A) guard should PASS -- the exemption regressed. Output: $(printf '%s' "$A_OUT" | tail -15)"
fi

# ── (B) a SIBLING file (same directory, different name) with the SAME raw
# call shape MUST still fail the guard -- proving the exemption is exact-path,
# not a directory-wide carve-out for 03-agent-browser/ ────────────────────────
echo ""
echo "--- (B) the SAME raw call shape in a SIBLING file under 03-agent-browser/scripts/ still fails the guard ---"
SIBLING="$TMP_TREE/03-agent-browser/scripts/zz-planted-sibling-probe.sh"
cat > "$SIBLING" <<'EOF'
#!/usr/bin/env bash
# Planted negative fixture (this test only) -- same raw-call shape as
# lib-backstop-conformance.sh, but NOT at the exempted path.
agent-browser --headed false open --session zz-planted "https://example.com"
EOF
B_OUT="$(bash "$GUARD" --repo-root "$TMP_TREE" 2>&1)"
B_EXIT=$?
if [[ "$B_EXIT" -ne 0 ]]; then
  pass "(B) guard FAILS (exit $B_EXIT) on the sibling file -- exemption is narrow, not directory-wide"
else
  fail "(B) guard did NOT bite the sibling file -- the exemption has widened to the whole 03-agent-browser/ directory (exit 0)"
fi
if printf '%s' "$B_OUT" | grep -q "03-agent-browser/scripts/zz-planted-sibling-probe.sh"; then
  pass "(B) guard's failure output names the planted SIBLING file"
else
  fail "(B) guard should name the sibling file (got: $(printf '%s' "$B_OUT" | grep -i 'fail\|zz-planted' | head -5 | tr '\n' ';'))"
fi
if printf '%s' "$B_OUT" | grep -q "03-agent-browser/scripts/lib-backstop-conformance.sh"; then
  fail "(B) guard's failure output should NOT name the exempted lib-backstop-conformance.sh"
else
  pass "(B) guard's failure output correctly does NOT name the exempted lib-backstop-conformance.sh"
fi
rm -f "$SIBLING"

# ── (C) tree passes again once the sibling fixture is removed ────────────────
echo ""
echo "--- (C) tree passes again once the sibling fixture is removed ---"
C_OUT="$(bash "$GUARD" --repo-root "$TMP_TREE" 2>&1)"
C_EXIT=$?
if [[ "$C_EXIT" -eq 0 ]]; then
  pass "(C) guard PASSES again after the sibling fixture is removed"
else
  fail "(C) guard should PASS once the fixture is removed. Output: $(printf '%s' "$C_OUT" | tail -15)"
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
