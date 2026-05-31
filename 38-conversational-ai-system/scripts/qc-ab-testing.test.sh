#!/usr/bin/env bash
# qc-ab-testing.test.sh — negative test for qc-ab-testing.sh (F16).
#
# A QC gate that can never fail is worthless. This proves qc-ab-testing.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F16 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. neuter the DETERMINISTIC-BY-CONTACT (sticky, stays-in-one-arm) assignment,
#         2. neuter the operator-only / never-customer-invoked (A/B-injection) guard,
#         3. drop the ab-test-events.jsonl seeding from the installer.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-ab-testing.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-ab-testing.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-ab-testing.test: negative test for the F16 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-ab-testing.sh"
else
  ng "intact skill should PASS qc-ab-testing.sh but it failed — run: bash $GATE"
fi

make_copy() {
  local dst; dst="$(mktemp -d)"
  cp -a "$SKILL_DIR/." "$dst/"
  printf '%s' "$dst"
}

run_should_fail() {
  local dir="$1" desc="$2"
  if bash "$GATE" --skill-dir "$dir" >/dev/null 2>&1; then
    ng "gate should FAIL when $desc — but it PASSED"
  else
    ok "gate correctly FAILS when $desc"
  fi
  rm -rf "$dir"
}

# (B1) Neuter the deterministic-by-contact / sticky / stays-in-one-arm assignment in the
#      protocol (replace every token that proves the assignment rule so it can't be shown).
D1="$(make_copy)"
TMP="$(mktemp)"
sed -e 's/deterministic[- ]by[- ]contact/AB_ASSIGN_REMOVED/Ig' \
    -e 's/deterministic_by_contact/AB_ASSIGN_REMOVED/g' \
    -e 's/stays in one arm/AB_ASSIGN_REMOVED/Ig' \
    -e 's/sticky/AB_ASSIGN_REMOVED/Ig' \
    -e 's/same variant/AB_ASSIGN_REMOVED/Ig' \
    -e 's/same arm/AB_ASSIGN_REMOVED/Ig' \
    "$D1/protocols/ab-testing-protocol.md" > "$TMP"; mv "$TMP" "$D1/protocols/ab-testing-protocol.md"
run_should_fail "$D1" "the deterministic-by-contact (sticky, stays-in-one-arm) assignment is neutered in the protocol"

# (B2) Neuter the operator-only / never-customer-invoked (A/B-injection) guard. The gate keys
#      on (operator-only) AND (the A/B-injection / experiment-control-instruction /
#      can-never-(define-or-alter|control)-an-experiment phrasing); strip BOTH halves so the
#      guard can no longer be proven (case-insensitive, so the uppercase OPERATOR-ONLY too).
D2="$(make_copy)"
TMP="$(mktemp)"
sed -E -e 's/[Oo][Pp][Ee][Rr][Aa][Tt][Oo][Rr]-only/AB_GUARD_REMOVED/g' \
       -e 's/[Oo][Pp][Ee][Rr][Aa][Tt][Oo][Rr] only/AB_GUARD_REMOVED/g' \
       -e 's/A\/B-injection/AB_GUARD_REMOVED/g' \
       -e 's/experiment-control instruction/AB_GUARD_REMOVED/g' \
       -e 's/can never define or alter (an )?(the )?experiment/CAN do whatever with the experiment/Ig' \
       -e 's/can never control (an )?(the )?experiment/now controls the experiment/Ig' \
    "$D2/protocols/ab-testing-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/ab-testing-protocol.md"
run_should_fail "$D2" "the operator-only / never-customer-invoked (A/B-injection) guard is neutered"

# (B3) Drop the ab-test-events.jsonl seeding from the installer.
D3="$(make_copy)"
TMP="$(mktemp)"; grep -v 'ab-test-events.jsonl' "$D3/scripts/25-seed-round3-feature-files.sh" > "$TMP"; mv "$TMP" "$D3/scripts/25-seed-round3-feature-files.sh"
run_should_fail "$D3" "the ab-test-events.jsonl sink is no longer seeded by the installer"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-ab-testing.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
