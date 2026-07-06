#!/usr/bin/env bash
# tests/unit/install-doc-consistency.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# F1.5 — proves shared-utils/prebuilt-index/assert-install-doc-consistency.py:
#   (1) PASSES against the real repo tree (INSTALL.md ↔ INDEX-MANIFEST.json),
#       allowing the single-step re-baseline seam as a NOTICE, not a failure;
#   (2) FAILS a grossly-stale INSTALL.md (the "48 personas" drift the guard exists
#       to catch);
#   (3) PASSES an exact-match fixture;
#   (4) PASSES an INSTALL.md that hardcodes NO persona count (the "drop it from
#       prose" remedy).
#
# Fully offline: no network, no embeddings. Exit 0 = all checks pass.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ASSERT="$REPO_ROOT/shared-utils/prebuilt-index/assert-install-doc-consistency.py"

PASS=0; FAIL=0
pass() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── 1) real tree passes (exit 0) ─────────────────────────────────────────────
if python3 "$ASSERT" >/dev/null 2>&1; then
    pass "1: real INSTALL.md ↔ manifest is consistent (exit 0)"
else
    fail "1: real tree FAILED the consistency guard (exit $?)"
fi

# ── 2) grossly-stale INSTALL.md fails against an 82-persona manifest ──────────
printf '{"persona_count": 82}\n' > "$TMP/manifest.json"
printf 'Download the prebuilt index with 48 personas ready to go.\n' > "$TMP/install-stale.md"
if python3 "$ASSERT" --install "$TMP/install-stale.md" --manifest "$TMP/manifest.json" >/dev/null 2>&1; then
    fail "2: stale '48 personas' vs manifest 82 was NOT caught (expected exit 1)"
else
    pass "2: stale '48 personas' vs manifest 82 correctly FAILS"
fi

# ── 3) exact-match fixture passes ────────────────────────────────────────────
printf 'The library ships 82 personas. Falls back for all 82 personas.\n' > "$TMP/install-ok.md"
if python3 "$ASSERT" --install "$TMP/install-ok.md" --manifest "$TMP/manifest.json" >/dev/null 2>&1; then
    pass "3: exact-match 82 vs 82 passes"
else
    fail "3: exact-match 82 vs 82 unexpectedly FAILED (exit $?)"
fi

# ── 4) no hardcoded count passes (drop-from-prose remedy) ────────────────────
printf 'The library ships the full canonical persona set (see the manifest).\n' > "$TMP/install-none.md"
if python3 "$ASSERT" --install "$TMP/install-none.md" --manifest "$TMP/manifest.json" >/dev/null 2>&1; then
    pass "4: INSTALL.md with no hardcoded persona count passes"
else
    fail "4: no-hardcoded-count INSTALL.md unexpectedly FAILED (exit $?)"
fi

# ── 5) one-step seam is a NOTICE, not a failure ──────────────────────────────
printf '{"persona_count": 81}\n' > "$TMP/manifest-81.json"
if python3 "$ASSERT" --install "$TMP/install-ok.md" --manifest "$TMP/manifest-81.json" >/dev/null 2>&1; then
    pass "5: 82 vs 81 re-baseline seam passes as a NOTICE"
else
    fail "5: one-step seam 82 vs 81 unexpectedly FAILED (exit $?)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
