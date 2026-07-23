#!/usr/bin/env bash
# test-u008-preflight-spend-check.sh — U008 verification.
#
# Tests u008_preflight_spend_check() in update-skills.sh: a pre-flight budget
# guard run BEFORE the paid-API steps (persona embedding, QC gates, floor-fill).
# It warns (or gates, with OPENCLAW_SPEND_GATE=1) when the org's remaining budget
# is below OPENCLAW_ORG_SPEND_LIMIT, so a depleted budget is never burned through
# silently — especially on fleet-wide rolls.
#
# Usage:
#   bash shared-utils/test-u008-preflight-spend-check.sh
#
# Pass criteria (all must hold):
#   1. bash -n update-skills.sh passes (AC#1).
#   2. The function is actually invoked in the update flow (not dead code).
#   3. AC#2: remaining < limit -> warning emitted (warn-only by default, rc 0).
#   4. AC#2: remaining < limit + OPENCLAW_SPEND_GATE=1 -> rc 1 (gate fires).
#   5. AC#3: remaining >= limit -> NO warning, rc 0 (proceeds unchanged).
#   6. Edge: remaining unset -> no-op, rc 0 (no false flag when no budget figure).
#   7. Edge: non-numeric remaining -> no-op, rc 0 (never crashes).
#
# The function is extracted from update-skills.sh and exercised directly, so the
# test is hermetic (no real box, no paid API calls) and does not run the full
# multi-thousand-line update flow.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/update-skills.sh"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

# ─── GUARD 1: bash -n (AC#1) ─────────────────────────────────────────────────
bash -n "$SCRIPT" || fail "bash -n update-skills.sh failed (AC#1)"
pass "bash -n update-skills.sh passes (AC#1)"

# ─── GUARD 2: the function is wired into the update flow (not dead code) ─────
grep -q 'u008_preflight_spend_check' "$SCRIPT" \
  || fail "u008_preflight_spend_check is not referenced in update-skills.sh"
# It must be CALLED (not just defined): a call line, not the definition line.
grep -q 'if ! u008_preflight_spend_check' "$SCRIPT" \
  || fail "u008_preflight_spend_check is defined but never called in the update flow"
pass "function is invoked in the update flow"

# ─── Extract the function under test ─────────────────────────────────────────
FUNC_SRC="$(sed -n '/^u008_preflight_spend_check() {/,/^}/p' "$SCRIPT")"
[ -n "$FUNC_SRC" ] || fail "could not extract u008_preflight_spend_check from update-skills.sh"
eval "$FUNC_SRC"

# ─── AC#2: remaining < limit -> warning (warn-only default, rc 0) ────────────
out="$(OPENCLAW_ORG_SPEND_LIMIT=100 OPENCLAW_ORG_SPEND_REMAINING=10 OPENCLAW_SPEND_GATE=0 \
  u008_preflight_spend_check; echo "rc=$?")"
rc="${out##*rc=}"; body="${out%rc=*}"
[ "$rc" = "0" ] || fail "AC#2: warn-only mode must return 0, got rc=$rc"
echo "$body" | grep -qi "PRE-FLIGHT SPEND CHECK (U008)" \
  || fail "AC#2: expected a spend-check warning, got: '$body'"
echo "$body" | grep -qi "BELOW" \
  || fail "AC#2: warning must state the budget is below the threshold, got: '$body'"
pass "AC#2: remaining < limit -> warning emitted (warn-only, rc 0)"

# ─── AC#2: remaining < limit + OPENCLAW_SPEND_GATE=1 -> rc 1 (gate) ──────────
out="$(OPENCLAW_ORG_SPEND_LIMIT=100 OPENCLAW_ORG_SPEND_REMAINING=10 OPENCLAW_SPEND_GATE=1 \
  u008_preflight_spend_check; echo "rc=$?")"
rc="${out##*rc=}"; body="${out%rc=*}"
[ "$rc" = "1" ] || fail "AC#2: gate mode below limit must return 1, got rc=$rc"
echo "$body" | grep -qi "GATING" \
  || fail "AC#2: gate mode must announce it is gating, got: '$body'"
pass "AC#2: remaining < limit + OPENCLAW_SPEND_GATE=1 -> gate fires (rc 1)"

# ─── AC#3: remaining >= limit -> NO warning, rc 0 (proceeds unchanged) ───────
out="$(OPENCLAW_ORG_SPEND_LIMIT=100 OPENCLAW_ORG_SPEND_REMAINING=500 OPENCLAW_SPEND_GATE=1 \
  u008_preflight_spend_check; echo "rc=$?")"
rc="${out##*rc=}"; body="${out%rc=*}"
[ "$rc" = "0" ] || fail "AC#3: sufficient budget must return 0, got rc=$rc"
[ -z "$body" ] || fail "AC#3: sufficient budget must emit NO warning, got: '$body'"
pass "AC#3: remaining >= limit -> no warning, rc 0 (unchanged)"

# ─── Edge: remaining unset -> no-op, rc 0 (no false flag) ────────────────────
out="$(unset OPENCLAW_ORG_SPEND_REMAINING; OPENCLAW_ORG_SPEND_LIMIT=100 OPENCLAW_SPEND_GATE=1 \
  u008_preflight_spend_check; echo "rc=$?")"
rc="${out##*rc=}"; body="${out%rc=*}"
[ "$rc" = "0" ] || fail "edge: unset remaining must return 0, got rc=$rc"
[ -z "$body" ] || fail "edge: unset remaining must emit NO warning, got: '$body'"
pass "edge: remaining unset -> no-op, rc 0 (no false flag)"

# ─── Edge: non-numeric remaining -> no-op, rc 0 (never crashes) ──────────────
out="$(OPENCLAW_ORG_SPEND_LIMIT=100 OPENCLAW_ORG_SPEND_REMAINING=not-a-number OPENCLAW_SPEND_GATE=1 \
  u008_preflight_spend_check; echo "rc=$?")"
rc="${out##*rc=}"; body="${out%rc=*}"
[ "$rc" = "0" ] || fail "edge: non-numeric remaining must return 0, got rc=$rc"
[ -z "$body" ] || fail "edge: non-numeric remaining must emit NO warning, got: '$body'"
pass "edge: non-numeric remaining -> no-op, rc 0 (never crashes)"

echo ""
echo "All U008 tests passed."
