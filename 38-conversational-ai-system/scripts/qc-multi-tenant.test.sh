#!/usr/bin/env bash
# qc-multi-tenant.test.sh — negative test for qc-multi-tenant.sh (F21).
#
# A QC gate that can never fail is worthless. This proves qc-multi-tenant.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F21 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. remove the hooks.mappings tenant_id convention from the protocol,
#         2. neuter the operator-only / never-customer-invoked guard,
#         3. drop the multi-tenant-events.jsonl seeding from the installer.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-multi-tenant.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-multi-tenant.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-multi-tenant.test: negative test for the F21 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-multi-tenant.sh"
else
  ng "intact skill should PASS qc-multi-tenant.sh but it failed — run: bash $GATE"
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

# (B1) Remove the hooks.mappings tenant_id convention (strip the "tenant_id" JSON key
#      lines from the protocol so the routing convention can't be proven).
D1="$(make_copy)"
TMP="$(mktemp)"; grep -v '"tenant_id"' "$D1/protocols/multi-tenant-isolation-protocol.md" > "$TMP"; mv "$TMP" "$D1/protocols/multi-tenant-isolation-protocol.md"
run_should_fail "$D1" "the hooks.mappings tenant_id convention is removed from the protocol"

# (B2) Neuter the operator-only / never-customer-invoked guard (case-insensitive so
#      both the "Operator-only" section header and inline "operator-only" are removed).
D2="$(make_copy)"
TMP="$(mktemp)"; sed 's/[Oo]perator-only/OPERATOR_GUARD_REMOVED/g' "$D2/protocols/multi-tenant-isolation-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/multi-tenant-isolation-protocol.md"
run_should_fail "$D2" "the operator-only / never-customer-invoked guard is neutered"

# (B3) Drop the multi-tenant-events.jsonl seeding from the installer.
D3="$(make_copy)"
TMP="$(mktemp)"; grep -v 'multi-tenant-events.jsonl' "$D3/scripts/25-seed-round3-feature-files.sh" > "$TMP"; mv "$TMP" "$D3/scripts/25-seed-round3-feature-files.sh"
run_should_fail "$D3" "the multi-tenant-events.jsonl sink is no longer seeded by the installer"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-multi-tenant.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
