#!/usr/bin/env bash
# qc-proactive-outreach.test.sh — negative test for qc-proactive-outreach.sh (F15).
#
# A QC gate that can never fail is worthless. This proves qc-proactive-outreach.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F15 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. neuter the STRICT quiet-hours respect (strip the Step 9.8 cross-reference),
#         2. neuter the operator-only / never-customer-invoked (outbound-injection) SEND guard,
#         3. drop the outreach-events.jsonl seeding from the installer.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-proactive-outreach.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-proactive-outreach.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-proactive-outreach.test: negative test for the F15 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-proactive-outreach.sh"
else
  ng "intact skill should PASS qc-proactive-outreach.sh but it failed — run: bash $GATE"
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

# (B1) Neuter the STRICT quiet-hours respect: strip every "Step 9.8" reference from the
#      protocol so the strict-quiet-hours invariant can't be proven.
D1="$(make_copy)"
TMP="$(mktemp)"; sed 's/Step 9\.8/Step REMOVED/g' "$D1/protocols/proactive-outreach-protocol.md" > "$TMP"; mv "$TMP" "$D1/protocols/proactive-outreach-protocol.md"
run_should_fail "$D1" "the STRICT quiet-hours respect (the Step 9.8 cross-reference) is removed from the protocol"

# (B2) Neuter the operator-only / never-customer-invoked (outbound-injection) SEND guard.
#      The gate's guard check needs (a) one of operator-only/operator only/allow-list AND
#      (b) one of never-customer / customer-never / outbound-injection / injection vector.
#      Strip BOTH groups case-insensitively (the protocol repeats the guard in several
#      places — heading, body, MEMORY rule, cross-refs — so the mutation must be thorough)
#      so the guard cannot be proven from the protocol any longer.
D2="$(make_copy)"
TMP="$(mktemp)"; sed -E \
  -e 's/[Oo][Pp][Ee][Rr][Aa][Tt][Oo][Rr]-[Oo][Nn][Ll][Yy]/OUTREACH_GUARD_REMOVED/g' \
  -e 's/[Oo][Pp][Ee][Rr][Aa][Tt][Oo][Rr] [Oo][Nn][Ll][Yy]/OUTREACH_GUARD_REMOVED/g' \
  -e 's/[Aa][Ll][Ll][Oo][Ww]-[Ll][Ii][Ss][Tt]/OUTREACH_GUARD_REMOVED/g' \
  -e 's/[Oo][Uu][Tt][Bb][Oo][Uu][Nn][Dd]-[Ii][Nn][Jj][Ee][Cc][Tt][Ii][Oo][Nn]/OUTREACH_GUARD_REMOVED/g' \
  -e 's/[Ii][Nn][Jj][Ee][Cc][Tt][Ii][Oo][Nn] [Vv][Ee][Cc][Tt][Oo][Rr]/OUTREACH_GUARD_REMOVED/g' \
  -e 's/[Cc][Aa][Nn] [Nn][Ee][Vv][Ee][Rr]/CAN/g' \
  -e 's/[Nn][Ee][Vv][Ee][Rr] [Cc][Uu][Ss][Tt][Oo][Mm][Ee][Rr]/now customer/g' \
  -e 's/[Nn][Ee][Vv][Ee][Rr]-[Cc][Uu][Ss][Tt][Oo][Mm][Ee][Rr]/now-customer/g' \
  -e "s/[Cc][Uu][Ss][Tt][Oo][Mm][Ee][Rr]'s name/contact NAME/g" \
  -e 's/[Cc][Uu][Ss][Tt][Oo][Mm][Ee][Rr] never/contact often/g' \
  -e 's/never re-pitch/often re-pitch/g' \
  "$D2/protocols/proactive-outreach-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/proactive-outreach-protocol.md"
run_should_fail "$D2" "the operator-only / never-customer-invoked (outbound-injection) SEND guard is neutered"

# (B3) Drop the outreach-events.jsonl seeding from the installer.
D3="$(make_copy)"
TMP="$(mktemp)"; grep -v 'outreach-events.jsonl' "$D3/scripts/25-seed-round3-feature-files.sh" > "$TMP"; mv "$TMP" "$D3/scripts/25-seed-round3-feature-files.sh"
run_should_fail "$D3" "the outreach-events.jsonl sink is no longer seeded by the installer"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-proactive-outreach.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
