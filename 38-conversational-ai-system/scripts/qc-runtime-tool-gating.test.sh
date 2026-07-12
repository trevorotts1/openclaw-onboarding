#!/usr/bin/env bash
# qc-runtime-tool-gating.test.sh - negative + positive fixture tests for
# qc-runtime-tool-gating.sh.
#
# Proves the gate:
#   * PASSES against the shipped skill (prover present + wired, fixture expresses
#     a real A-granted/B-denied gating boundary, Layer-A dry-run green), and
#   * FAILS (naming book_appointment) when the fixture's active phase is mutated
#     to ALSO grant book_appointment - i.e. the gating boundary is destroyed and
#     the prover would no longer be proving anything.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE_NAME="qc-runtime-tool-gating.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- POSITIVE: the shipped skill passes. ---------------------------------
GOOD="$TMP/good"
cp -r "$SKILL_DIR" "$GOOD"
if bash "$GOOD/scripts/$GATE_NAME" --skill-dir "$GOOD" >/dev/null 2>&1; then
  ok "shipped skill: gate PASSES (prover wired + fixture boundary real + Layer-A green)"
else
  bad "shipped skill: expected the gate to PASS"
  bash "$GOOD/scripts/$GATE_NAME" --skill-dir "$GOOD" 2>&1 | sed 's/^/      /'
fi

# --- NEGATIVE: mutate the fixture so the active phase ALSO grants tool B. -
BAD="$TMP/bad"
cp -r "$SKILL_DIR" "$BAD"
BAD_FIXTURE="$BAD/tools/tests/fixtures/runtime-gating-playbook.md"
# Phase 1 is the active phase; give it book_appointment (destroying the boundary).
python3 - "$BAD_FIXTURE" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace(
    "### Phase 1 - Gather context and check availability\ntools: check_availability, update_contact, update_tags, reference_documents",
    "### Phase 1 - Gather context and check availability\ntools: check_availability, book_appointment, update_contact, update_tags, reference_documents",
)
open(p, "w", encoding="utf-8").write(s)
PY

BOUT="$(bash "$BAD/scripts/$GATE_NAME" --skill-dir "$BAD" 2>&1)"
BRC=0
bash "$BAD/scripts/$GATE_NAME" --skill-dir "$BAD" >/dev/null 2>&1 || BRC=$?
[ "$BRC" != "0" ] && ok "mutated fixture: gate FAILS (exit $BRC)" || bad "mutated fixture: expected a non-zero exit"
printf '%s' "$BOUT" | grep -q "book_appointment" && ok "mutated fixture: gate names book_appointment as the broken boundary" || bad "mutated fixture: did not name book_appointment"

echo ""
echo "qc-runtime-tool-gating tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
