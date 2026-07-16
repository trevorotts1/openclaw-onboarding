#!/usr/bin/env bash
# tests/unit/page-qc-gate-guard.test.sh — U25/B-U11 binary acceptance (e):
# "the 8.5 threshold is asserted by the extended guard-fab-qc-gate.sh (a seeded
# 8.4-passes patch fails the guard)".
#
# Copies the small set of real files scripts/guard-fab-qc-gate.sh actually reads
# (universal-sops/, shared-utils/, the two skill wrapper/dispatcher/doc files) into
# an isolated tmp tree so the guard runs standalone (ROOT is derived from the
# script's own BASH_SOURCE location) — hermetic, fast, and faithful (real files,
# not synthetic stand-ins), unlike a hand-built minimal fixture that would have to
# re-derive every unrelated check's passing shape.
#
# Case 1: an UNMODIFIED copy of the real repo state -> guard PASSES (sanity: our
#         copy is faithful, not a strawman).
# Case 2: shared-utils/page_qc.py's THRESHOLD patched 8.5 -> 8.4 -> guard FAILS,
#         naming the Page-QC v2 threshold check specifically.
#
# Exit 0 = both cases behave as required. Exit 1 = the guard failed to catch the
# seeded regression (CI FAIL).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== page-qc-gate-guard.test.sh (U25/B-U11 acceptance item e) ==="

TMP_TREE="$(mktemp -d)"
trap 'rm -rf "$TMP_TREE"' EXIT

# NOTE (U117/E6-3/G9 merge-writer, 2026-07-16): this directory list had
# drifted stale against guard-fab-qc-gate.sh's OWN growth — the guard picked
# up checks reading 49-signature-funnel/ and tests/unit/ (U10's anti-copy
# guard proof, U117's own two new proof files) that this list never copied,
# so "Case 1: unmodified copy -> PASS" was silently failing before this fix
# (proof: `git stash && bash tests/unit/page-qc-gate-guard.test.sh` on the
# pre-U117 tree reproduces the failure). Corrected to the full union of
# every top-level dir any `$ROOT/...` reference in guard-fab-qc-gate.sh
# resolves into, same derivation tests/unit/u117-comms-qc-guard.test.sh uses.
for d in universal-sops shared-utils scripts tests \
         06-ghl-install-pages 44-convert-and-flow-operator \
         49-signature-funnel 22-book-to-persona-coaching-leadership-system; do
  mkdir -p "$TMP_TREE/$d"
  cp -a "$REPO_ROOT/$d/." "$TMP_TREE/$d/"
done

GUARD="$TMP_TREE/scripts/guard-fab-qc-gate.sh"
[[ -f "$GUARD" ]] || { echo "FAIL: guard copy missing at $GUARD"; exit 1; }
chmod +x "$GUARD"

# ── Case 1: unmodified copy -> PASS (proves the copy itself is faithful) ─────
if OUT1="$(bash "$GUARD" 2>&1)"; then
  pass "unmodified copy: guard PASSES (case 1 sanity)"
else
  fail "unmodified copy: guard FAILED unexpectedly — copy is not faithful:"
  echo "$OUT1" | sed 's/^/    /'
fi

# ── Case 2: seed an 8.4 threshold regression in the COPY only ────────────────
PAGE_QC_COPY="$TMP_TREE/shared-utils/page_qc.py"
if ! grep -q '^assert THRESHOLD == 8.5$' "$PAGE_QC_COPY"; then
  fail "cannot locate 'assert THRESHOLD == 8.5' in the copied page_qc.py to seed the regression"
else
  # Patch BOTH the reused-from-fab_qc assertion AND force a standalone constant so
  # the guard's `assert page_qc.THRESHOLD==8.5` import-time check actually sees 8.4
  # regardless of how the module derives THRESHOLD internally.
  python3 - "$PAGE_QC_COPY" <<'PY'
import sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
src = src.replace(
    'THRESHOLD = fab_qc.THRESHOLD  # 8.5 — never a new threshold\nassert THRESHOLD == 8.5',
    'THRESHOLD = 8.4  # SEEDED REGRESSION for page-qc-gate-guard.test.sh — must be caught',
)
open(path, "w", encoding="utf-8").write(src)
PY
  if OUT2="$(bash "$GUARD" 2>&1)"; then
    fail "seeded 8.4 THRESHOLD: guard PASSED (should have FAILED) — threshold regression not caught"
    echo "$OUT2" | sed 's/^/    /'
  else
    if echo "$OUT2" | grep -q "Page-QC v2 failed import / weights!=100 / threshold!=8.5"; then
      pass "seeded 8.4 THRESHOLD: guard FAILS and names the Page-QC v2 threshold check"
    else
      fail "seeded 8.4 THRESHOLD: guard failed but did NOT name the Page-QC v2 threshold check:"
      echo "$OUT2" | sed 's/^/    /'
    fi
  fi
fi

echo ""
echo "=== page-qc-gate-guard.test.sh: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
