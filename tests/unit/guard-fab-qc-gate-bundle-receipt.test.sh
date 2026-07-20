#!/usr/bin/env bash
# tests/unit/guard-fab-qc-gate-bundle-receipt.test.sh — B-U8/U22 binary
# acceptance (a): "the extended guard-fab-qc-gate.sh (bundle-receipt schema
# check ... ) — PASS/FAIL", proven by seeding each of the ways the schema
# check could silently stop biting and confirming the guard catches every one.
#
# Same isolated-tmp-tree strategy as tests/unit/page-qc-gate-guard.test.sh
# (real files copied into a scratch dir so the guard runs standalone,
# ROOT derived from its own BASH_SOURCE) — hermetic, fast, faithful.
#
# Case 1: an UNMODIFIED copy -> guard PASSES (sanity: the copy is faithful).
# Case 2: the schema FILE deleted -> guard FAILS naming the missing schema.
# Case 3: the validator's own self-test broken (validate_receipt always
#         returns True) -> guard FAILS naming the validator self-test check.
# Case 4: the ladder's produced receipt schema-broken (drops the required
#         'hold' key before the receipt is written) -> guard FAILS naming the
#         real-receipt-vs-schema check specifically.
#
# Exit 0 = all four cases behave as required. Exit 1 = the guard failed to
# catch a seeded regression (CI FAIL).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== guard-fab-qc-gate-bundle-receipt.test.sh (B-U8/U22 acceptance (a)) ==="

new_tree() {
  local dir; dir="$(mktemp -d)"
  for d in universal-sops shared-utils scripts tests \
           06-ghl-install-pages 44-convert-and-flow-operator \
           49-signature-funnel \
           22-book-to-persona-coaching-leadership-system; do
    mkdir -p "$dir/$d"
    cp -a "$REPO_ROOT/$d/." "$dir/$d/"
  done
  echo "$dir"
}

# ── Case 1: unmodified copy -> PASS ──────────────────────────────────────────
TREE1="$(new_tree)"
if OUT1="$(bash "$TREE1/scripts/guard-fab-qc-gate.sh" 2>&1)"; then
  pass "unmodified copy: guard PASSES (case 1 sanity)"
else
  fail "unmodified copy: guard FAILED unexpectedly — copy is not faithful:"
  echo "$OUT1" | sed 's/^/    /'
fi
rm -rf "$TREE1"

# ── Case 2: schema file deleted ──────────────────────────────────────────────
TREE2="$(new_tree)"
rm -f "$TREE2/shared-utils/persona-bundle-receipt.schema.json"
if OUT2="$(bash "$TREE2/scripts/guard-fab-qc-gate.sh" 2>&1)"; then
  fail "deleted schema file: guard PASSED (should have FAILED)"
  echo "$OUT2" | sed 's/^/    /'
else
  if echo "$OUT2" | grep -q "MISSING shared-utils/persona-bundle-receipt.schema.json"; then
    pass "deleted schema file: guard FAILS and names the missing schema"
  else
    fail "deleted schema file: guard failed but did NOT name the missing schema:"
    echo "$OUT2" | sed 's/^/    /'
  fi
fi
rm -rf "$TREE2"

# ── Case 3: validator self-test broken (validate_receipt always passes) ─────
TREE3="$(new_tree)"
VALIDATOR_COPY="$TREE3/shared-utils/persona_bundle_receipt_schema.py"
if ! grep -q "^def validate_receipt" "$VALIDATOR_COPY"; then
  fail "cannot locate 'def validate_receipt' in the copied validator to seed the regression"
else
  python3 - "$VALIDATOR_COPY" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
marker = "def validate_receipt(receipt: dict, schema: dict | None = None) -> tuple[bool, list[str]]:"
idx = src.index(marker)
insert_at = src.index('"""', src.index('"""', idx) + 3) + 3
seeded = "\n    return True, []  # SEEDED REGRESSION for guard-fab-qc-gate-bundle-receipt.test.sh — must be caught\n"
src = src[:insert_at] + seeded + src[insert_at:]
open(path, "w", encoding="utf-8").write(src)
PY
  if OUT3="$(bash "$TREE3/scripts/guard-fab-qc-gate.sh" 2>&1)"; then
    fail "seeded always-pass validator: guard PASSED (should have FAILED) — self-test regression not caught"
    echo "$OUT3" | sed 's/^/    /'
  else
    if echo "$OUT3" | grep -q "bundle-receipt schema validator self-test FAILED"; then
      pass "seeded always-pass validator: guard FAILS and names the validator self-test check"
    else
      fail "seeded always-pass validator: guard failed but did NOT name the self-test check:"
      echo "$OUT3" | sed 's/^/    /'
    fi
  fi
fi
rm -rf "$TREE3"

# ── Case 4: the ladder's real receipt drops the required 'hold' key ─────────
TREE4="$(new_tree)"
LADDER_COPY="$TREE4/06-ghl-install-pages/tools/persona_bundle_ladder.py"
if ! grep -q '"hold": hold,' "$LADDER_COPY"; then
  fail "cannot locate '\"hold\": hold,' in the copied ladder to seed the regression"
else
  python3 - "$LADDER_COPY" <<'PY'
import sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
assert '"hold": hold,\n' in src, "anchor line not found"
src = src.replace('"hold": hold,\n', '', 1)
open(path, "w", encoding="utf-8").write(src)
PY
  if OUT4="$(bash "$TREE4/scripts/guard-fab-qc-gate.sh" 2>&1)"; then
    fail "seeded receipt missing 'hold': guard PASSED (should have FAILED) — real-receipt check not catching drift"
    echo "$OUT4" | sed 's/^/    /'
  else
    if echo "$OUT4" | grep -q "a REAL persona_bundle_ladder receipt FAILED schema validation"; then
      pass "seeded receipt missing 'hold': guard FAILS and names the real-receipt-vs-schema check"
    else
      fail "seeded receipt missing 'hold': guard failed but did NOT name the real-receipt check:"
      echo "$OUT4" | sed 's/^/    /'
    fi
  fi
fi
rm -rf "$TREE4"

echo ""
echo "=== guard-fab-qc-gate-bundle-receipt.test.sh: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
