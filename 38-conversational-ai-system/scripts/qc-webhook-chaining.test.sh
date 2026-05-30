#!/usr/bin/env bash
# qc-webhook-chaining.test.sh — negative test for qc-webhook-chaining.sh (F18).
#
# A QC gate that can never fail is worthless. This proves qc-webhook-chaining.sh:
#   (A) PASSES on the real, intact skill tree, and
#   (B) FAILS (exit non-zero) when an F18 invariant is broken — here we break THREE
#       different invariants in three throwaway copies:
#         1. neuter the operator-only / never-customer-invoked OUTBOUND (SSRF/
#            exfiltration) guard,
#         2. neuter the retry policy (exponential backoff + max attempts),
#         3. drop the webhook-chain-events.jsonl seeding from the installer.
#
# BASH only (no .py) so it respects qc-static's claude-/anthropic ban. Self-contained:
# copies the skill to a temp dir, mutates the copy, runs the gate against --skill-dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-webhook-chaining.sh"

[ -f "$GATE" ] || { echo "FAIL: qc-webhook-chaining.sh not found at $GATE"; exit 1; }

RC=0
ok()   { echo "  [TEST PASS] $1"; }
ng()   { echo "  [TEST FAIL] $1"; RC=1; }

echo "=== qc-webhook-chaining.test: negative test for the F18 gate ==="

# (A) The intact skill must PASS.
if bash "$GATE" --skill-dir "$SKILL_DIR" >/dev/null 2>&1; then
  ok "intact skill passes qc-webhook-chaining.sh"
else
  ng "intact skill should PASS qc-webhook-chaining.sh but it failed — run: bash $GATE"
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

# (B1) Neuter the operator-only / never-customer-invoked OUTBOUND (SSRF/exfiltration)
#      guard. The gate keys on (operator-only/operator-defined) AND (SSRF / exfiltration /
#      customer-can-never-supply-a-target phrasing); strip BOTH halves so the guard can no
#      longer be proven (case-insensitive).
D1="$(make_copy)"
TMP="$(mktemp)"
sed -E -e 's/operator-only/WEBHOOK_GUARD_REMOVED/Ig' \
       -e 's/operator only/WEBHOOK_GUARD_REMOVED/Ig' \
       -e 's/operator-defined/WEBHOOK_GUARD_REMOVED/Ig' \
       -e 's/SSRF/WEBHOOK_GUARD_REMOVED/Ig' \
       -e 's/exfiltration/WEBHOOK_GUARD_REMOVED/Ig' \
       -e 's/never fires a POST to a URL a CUSTOMER supplied/happily POSTs to any URL/Ig' \
       -e 's/never POSTs to a customer-supplied/now POSTs to a customer-supplied/Ig' \
       -e 's/customer can never (name|add|trigger|supply)/customer may freely \1/Ig' \
    "$D1/protocols/webhook-chaining-protocol.md" > "$TMP"; mv "$TMP" "$D1/protocols/webhook-chaining-protocol.md"
run_should_fail "$D1" "the operator-only / never-customer-invoked OUTBOUND (SSRF/exfiltration) guard is neutered"

# (B2) Neuter the retry policy. The gate keys on (backoff) AND (exponential) AND
#      (max_attempts); strip all three so the bounded-retry invariant can no longer be
#      proven.
D2="$(make_copy)"
TMP="$(mktemp)"
sed -E -e 's/exponential/instant-forever/Ig' \
       -e 's/backoff/RETRY_REMOVED/Ig' \
       -e 's/max_attempts/RETRY_REMOVED/Ig' \
       -e 's/max attempts/RETRY_REMOVED/Ig' \
    "$D2/protocols/webhook-chaining-protocol.md" > "$TMP"; mv "$TMP" "$D2/protocols/webhook-chaining-protocol.md"
run_should_fail "$D2" "the retry policy (exponential backoff + max attempts) is neutered"

# (B3) Drop the webhook-chain-events.jsonl seeding from the installer.
D3="$(make_copy)"
TMP="$(mktemp)"; grep -v 'webhook-chain-events.jsonl' "$D3/scripts/25-seed-round3-feature-files.sh" > "$TMP"; mv "$TMP" "$D3/scripts/25-seed-round3-feature-files.sh"
run_should_fail "$D3" "the webhook-chain-events.jsonl sink is no longer seeded by the installer"

echo ""
if [ "$RC" -eq 0 ]; then
  echo "RESULT: PASS — qc-webhook-chaining.sh passes intact and fails on each broken invariant."
  exit 0
else
  echo "RESULT: FAIL — the negative test did not behave as expected (see above)."
  exit 1
fi
