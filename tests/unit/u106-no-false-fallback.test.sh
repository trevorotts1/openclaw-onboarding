#!/usr/bin/env bash
# tests/unit/u106-no-false-fallback.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# U106 — Summarize-YouTube remove false auto-fallback claim.
#
# Proves that:
#   1. summarize-youtube-full.md no longer claims a runtime auto-fallback exists
#      (the "The skill's runtime logic will detect" paragraph was removed)
#   2. The document marks the VPS path as UNSUPPORTED and says "no runtime
#      auto-fallback" (the correction was applied)
#   3. INSTALL.md fails closed on unsupported platforms with a platform guard
#   4. INSTALL.md explicitly documents "no runtime auto-fallback"
#   5. The Gemini retry in the examples is NOT a byte-identical self-chain
#      (it names --provider gemini on the second invocation)
#
# Hermetic: reads doc files only, no network, no binaries, no HOME mutation.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FULL_DOC="$REPO_ROOT/16-summarize-youtube/summarize-youtube-full.md"
INSTALL_DOC="$REPO_ROOT/16-summarize-youtube/INSTALL.md"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== U106 — no false auto-fallback claim ==="
echo ""

# ── 1) The old false claim must NOT appear anywhere in the full doc ──────────
if grep -qF "The skill's runtime logic will detect the missing" "$FULL_DOC"; then
  fail "1: full doc STILL contains the false auto-fallback claim"
else
  pass "1: full doc does NOT contain the false auto-fallback claim"
fi

# ── 2) The UNSUPPORTED admonition must be present ────────────────────────────
if grep -qF "UNSUPPORTED on this platform" "$FULL_DOC"; then
  pass "2: full doc contains 'UNSUPPORTED on this platform' admonition"
else
  fail "2: full doc MISSING the 'UNSUPPORTED on this platform' admonition"
fi

# ── 3) The full doc must explicitly say "no runtime auto-fallback" ───────────
if grep -qF "no runtime auto-fallback" "$FULL_DOC"; then
  pass "3: full doc states 'no runtime auto-fallback'"
else
  fail "3: full doc does NOT state 'no runtime auto-fallback'"
fi

# ── 4) The full doc must state that the install FAILS CLOSED ─────────────────
if grep -qF "FAILS CLOSED" "$FULL_DOC"; then
  pass "4: full doc documents 'FAILS CLOSED at install time'"
else
  fail "4: full doc MISSING 'FAILS CLOSED' language"
fi

# ── 5) The full doc provider-fallback example must name --provider gemini ─────
if grep -qF -- "--provider gemini" "$FULL_DOC"; then
  pass "5: full doc Gemini retry includes '--provider gemini'"
else
  fail "5: full doc Gemini retry MISSING '--provider gemini'"
fi

# ── 6) INSTALL.md must have the platform guard (fail-closed for VPS) ─────────
if grep -qF "UNSUPPORTED PLATFORM" "$INSTALL_DOC"; then
  pass "6: INSTALL.md has the UNSUPPORTED PLATFORM guard"
else
  fail "6: INSTALL.md MISSING the UNSUPPORTED PLATFORM guard"
fi

# ── 7) INSTALL.md platform guard must check for /data/.openclaw ─────────────
if grep -qF "/data/.openclaw" "$INSTALL_DOC"; then
  pass "7: INSTALL.md platform guard checks for /data/.openclaw"
else
  fail "7: INSTALL.md platform guard does NOT check for /data/.openclaw"
fi

# ── 8) INSTALL.md must also say "no runtime auto-fallback" ───────────────────
if grep -qF "no runtime auto-fallback" "$INSTALL_DOC"; then
  pass "8: INSTALL.md states 'no runtime auto-fallback'"
else
  fail "8: INSTALL.md does NOT state 'no runtime auto-fallback'"
fi

# ── 9) INSTALL.md missing-binary check must exit nonzero ────────────────────
if grep -qF "if ! summarize --help" "$INSTALL_DOC"; then
  pass "9: INSTALL.md checks summarize binary is callable after brew install"
else
  fail "9: INSTALL.md MISSING summarize binary callability check"
fi

# ── 10) INSTALL.md missing-binary failure message ────────────────────────────
if grep -qF "There is no fallback path" "$INSTALL_DOC"; then
  pass "10: INSTALL.md binary check says 'There is no fallback path'"
else
  fail "10: INSTALL.md binary check MISSING 'There is no fallback path'"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "PASS: all assertions for U106 pass"
exit 0
