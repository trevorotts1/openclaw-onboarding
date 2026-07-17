#!/usr/bin/env bash
# tests/unit/u117-comms-qc-guard.test.sh — U117 (E6-3/G9) BINARY acceptance (e):
# "the CI conformance guard FAILS on a scratch-branch mutation skipping the
# audience prompt or the topic slot on a comms path, then passes when
# restored (mutation proof)".
#
# Mirrors the established mutation-proof pattern this repo already uses
# (tests/unit/page-qc-gate-guard.test.sh, U25/B-U11 acceptance item e):
# copies the real files scripts/guard-fab-qc-gate.sh actually reads into an
# isolated tmp tree so the guard runs standalone (hermetic, fast, real
# files — not a hand-built strawman fixture). Directory list is the FULL
# union of every top-level dir any `$ROOT/...` reference in the guard
# script resolves into (derived directly from the script, not copy-pasted
# from the older sibling test — that one's list has drifted stale as the
# guard grew more checks over time; this test's own sanity case below would
# catch the same drift here if it ever happens again).
#
# Case 1: seed a mutation on the comms-conformance PATH that removes the
#         audience-confirmed check entirely (the literal ADD-2 "skip the
#         audience prompt" regression this unit's own acceptance text names)
#         -> the extended guard-fab-qc-gate.sh FAILS, naming the U117
#         conformance-invariant check specifically.
# Case 2: RESTORE the unmutated file over the mutated copy -> guard PASSES
#         again (the literal "then passes when restored" order the spec
#         text asks for).
# Case 3: seed the SIBLING mutation — remove the topic-considered check
#         instead ("skip the topic slot") -> guard FAILS again, independent
#         of case 1/2 (both named regressions are separately caught, not
#         just one).
# Case 4: restore again -> guard PASSES (confirms case 3's mutation is also
#         cleanly reversible, not a false-positive-by-accident).
#
# Exit 0 = all four cases behave as required. Exit 1 = the guard failed to
# catch a seeded regression (CI FAIL).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== u117-comms-qc-guard.test.sh (U117/E6-3/G9 acceptance item e) ==="

TMP_TREE="$(mktemp -d)"
trap 'rm -rf "$TMP_TREE"' EXIT

for d in universal-sops shared-utils scripts tests \
         06-ghl-install-pages 44-convert-and-flow-operator \
         49-signature-funnel 22-book-to-persona-coaching-leadership-system; do
  mkdir -p "$TMP_TREE/$d"
  cp -a "$REPO_ROOT/$d/." "$TMP_TREE/$d/"
done

GUARD="$TMP_TREE/scripts/guard-fab-qc-gate.sh"
[[ -f "$GUARD" ]] || { echo "FAIL: guard copy missing at $GUARD"; exit 1; }
chmod +x "$GUARD"

PAGE_QC_COPY="$TMP_TREE/shared-utils/page_qc.py"
[[ -f "$PAGE_QC_COPY" ]] || { echo "FAIL: page_qc.py copy missing at $PAGE_QC_COPY"; exit 1; }
ORIGINAL_PAGE_QC="$(cat "$PAGE_QC_COPY")"

restore_page_qc() { printf '%s' "$ORIGINAL_PAGE_QC" > "$PAGE_QC_COPY"; }

# ── sanity: the unmodified copy passes BEFORE any mutation ───────────────────
if OUT0="$(bash "$GUARD" 2>&1)"; then
  pass "unmodified copy: guard PASSES (sanity — the copy itself is faithful)"
else
  fail "unmodified copy: guard FAILED unexpectedly — copy is not faithful:"
  echo "$OUT0" | sed 's/^/    /'
fi

# ── Case 1: seed "skip the audience prompt" — delete check_audience_confirmed
#            (the deterministic ADD-2 audience-recorded check) from the copy ──
python3 - "$PAGE_QC_COPY" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
# Remove the whole function definition (up to the next top-level `def `/blank-
# line-then-def boundary) so any call site referencing it also breaks loudly —
# a real "the check no longer exists" regression, not a cosmetic rename.
pattern = re.compile(
    r"def check_audience_confirmed\(inp: dict\) -> Dim:.*?\n\n\n", re.DOTALL)
new_src, n = pattern.subn("", src, count=1)
assert n == 1, "seed-mutation anchor not found — page_qc.py shape drifted"
open(path, "w", encoding="utf-8").write(new_src)
PY
if OUT1="$(bash "$GUARD" 2>&1)"; then
  fail "seeded 'skip audience prompt' mutation: guard PASSED (should have FAILED)"
  echo "$OUT1" | sed 's/^/    /'
else
  if echo "$OUT1" | grep -q "U117 comms conformance invariant REGRESSED"; then
    pass "seeded 'skip audience prompt' mutation: guard FAILS and names the U117 conformance invariant"
  else
    fail "seeded 'skip audience prompt' mutation: guard failed but did NOT name the U117 check:"
    echo "$OUT1" | sed 's/^/    /'
  fi
fi

# ── Case 2: RESTORE -> guard PASSES again ─────────────────────────────────────
restore_page_qc
if OUT2="$(bash "$GUARD" 2>&1)"; then
  pass "restored after 'skip audience prompt' mutation: guard PASSES again"
else
  fail "restored copy still FAILS the guard — restore did not take:"
  echo "$OUT2" | sed 's/^/    /'
fi

# ── Case 3: seed "skip the topic slot" — delete check_topic_considered ───────
python3 - "$PAGE_QC_COPY" <<'PY'
import re, sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()
pattern = re.compile(
    r"def check_topic_considered\(inp: dict\) -> Dim:.*?\n\n\n", re.DOTALL)
new_src, n = pattern.subn("", src, count=1)
assert n == 1, "seed-mutation anchor not found — page_qc.py shape drifted"
open(path, "w", encoding="utf-8").write(new_src)
PY
if OUT3="$(bash "$GUARD" 2>&1)"; then
  fail "seeded 'skip topic slot' mutation: guard PASSED (should have FAILED)"
  echo "$OUT3" | sed 's/^/    /'
else
  if echo "$OUT3" | grep -q "U117 comms conformance invariant REGRESSED"; then
    pass "seeded 'skip topic slot' mutation: guard FAILS and names the U117 conformance invariant"
  else
    fail "seeded 'skip topic slot' mutation: guard failed but did NOT name the U117 check:"
    echo "$OUT3" | sed 's/^/    /'
  fi
fi

# ── Case 4: RESTORE again -> guard PASSES ─────────────────────────────────────
restore_page_qc
if OUT4="$(bash "$GUARD" 2>&1)"; then
  pass "restored after 'skip topic slot' mutation: guard PASSES again"
else
  fail "restored copy still FAILS the guard — restore did not take:"
  echo "$OUT4" | sed 's/^/    /'
fi

echo ""
echo "=== u117-comms-qc-guard.test.sh: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
