#!/usr/bin/env bash
# qc-segmentation.test.sh — negative test for qc-segmentation.sh (F17).
#
# A QC gate that can never fail is worthless. This proves qc-segmentation.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F17 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. delete the multi-tag precedence line from the protocol,
#         2. neuter the operator-only / never-customer-invoked (self-promotion) guard,
#         3. drop the segmentation-events.jsonl seeding from the installer.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-segmentation.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-segmentation.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-segmentation.test: negative test for the F17 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-segmentation.sh"
else
  ng "intact skill should PASS qc-segmentation.sh but it failed — run: bash $GATE"
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

# (B1) Remove the multi-tag precedence line from the protocol (strip every line that
#      states the precedence ordering so the resolution rule can't be proven).
D1="$(make_copy)"
TMP="$(mktemp)"; grep -v 'at-risk .* vip .* churned .* returning .* prospect' "$D1/protocols/customer-segmentation-protocol.md" > "$TMP"; mv "$TMP" "$D1/protocols/customer-segmentation-protocol.md"
run_should_fail "$D1" "the multi-tag precedence (at-risk > vip > churned > returning > prospect) is removed from the protocol"

# (B2) Neuter the operator-only / never-customer-invoked (self-promotion) guard
#      (replace the guard tokens so neither "operator-only/operator-owned" nor the
#      "customer can never / self-promotion" language survives).
D2="$(make_copy)"
TMP="$(mktemp)"; sed -e 's/[Oo]perator-only/SEG_GUARD_REMOVED/g' -e 's/[Oo]perator-owned/SEG_GUARD_REMOVED/g' -e 's/self-promotion/SEG_GUARD_REMOVED/g' -e 's/can never set/CAN do whatever/g' -e 's/never claimed by the customer/now claimable/g' "$D2/protocols/customer-segmentation-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/customer-segmentation-protocol.md"
run_should_fail "$D2" "the operator-only / never-customer-invoked (self-promotion) guard is neutered"

# (B3) Drop the segmentation-events.jsonl seeding from the installer.
D3="$(make_copy)"
TMP="$(mktemp)"; grep -v 'segmentation-events.jsonl' "$D3/scripts/25-seed-round3-feature-files.sh" > "$TMP"; mv "$TMP" "$D3/scripts/25-seed-round3-feature-files.sh"
run_should_fail "$D3" "the segmentation-events.jsonl sink is no longer seeded by the installer"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-segmentation.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
