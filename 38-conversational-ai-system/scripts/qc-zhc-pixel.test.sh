#!/usr/bin/env bash
# qc-zhc-pixel.test.sh — negative test for qc-zhc-pixel.sh.
#
# A QC gate that can never fail is worthless. This proves qc-zhc-pixel.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F49 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. remove the pixel-visitor-signal hook registration,
#         2. drop a required ZHC_ field from the protocol,
#         3. neuter the scope precheck (remove a required scope name).
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-zhc-pixel.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-zhc-pixel.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-zhc-pixel.test: negative test for the F49 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-zhc-pixel.sh"
else
  ng "intact skill should PASS qc-zhc-pixel.sh but it failed — run: bash $GATE"
fi

make_copy() {
  local dst; dst="$(mktemp -d)"
  # cp the skill tree (portable; -a keeps modes). Exclude nothing — small tree.
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

# (B1) Remove the hook registration id.
D1="$(make_copy)"
# Strip the literal pixel-visitor-signal token from the hook configurator.
TMP="$(mktemp)"; grep -v 'pixel-visitor-signal' "$D1/scripts/28-configure-pixel-hook.sh" > "$TMP"; mv "$TMP" "$D1/scripts/28-configure-pixel-hook.sh"
run_should_fail "$D1" "the pixel-visitor-signal hook registration is removed"

# (B2) Drop a required ZHC_ field from the protocol.
D2="$(make_copy)"
TMP="$(mktemp)"; sed 's/ZHC_high_intent_signal/REMOVED_FIELD/g' "$D2/protocols/zhc-pixel-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/zhc-pixel-protocol.md"
# also remove from AGENTS updater so the OR-match can't find it
TMP="$(mktemp)"; sed 's/ZHC_high_intent_signal/REMOVED_FIELD/g' "$D2/scripts/05-update-agents-md.sh" > "$TMP"; mv "$TMP" "$D2/scripts/05-update-agents-md.sh"
run_should_fail "$D2" "a required ZHC_ field (ZHC_high_intent_signal) is dropped"

# (B3) Neuter the scope precheck (remove a required scope name).
D3="$(make_copy)"
TMP="$(mktemp)"; sed 's/Workers Routes:Edit/Workers Routes Edit REMOVED/g' "$D3/scripts/26-verify-pixel-prerequisites.sh" > "$TMP"; mv "$TMP" "$D3/scripts/26-verify-pixel-prerequisites.sh"
run_should_fail "$D3" "the precheck no longer names the Workers Routes:Edit scope"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-zhc-pixel.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
