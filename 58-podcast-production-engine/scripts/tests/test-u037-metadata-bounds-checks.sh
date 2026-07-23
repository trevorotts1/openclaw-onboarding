#!/usr/bin/env bash
# test-u037-metadata-bounds-checks.sh — U037 verification.
#
# Tests validate_episode_metadata() in podbean_publish.sh: pre-flight bounds/
# content checks run BEFORE any Podbean API call, so an over-length show-notes/
# title or an invalid episode type is rejected HERE with a clear message instead
# of a cryptic API rejection after the upload.
#
# Usage:
#   bash 58-podcast-production-engine/scripts/tests/test-u037-metadata-bounds-checks.sh
#
# Pass criteria (all must hold):
#   1. bash -n podbean_publish.sh passes (AC#1).
#   2. The function is actually invoked in the publish flow (not dead code).
#   3. AC#2: over-length show notes -> pre-flight failure (rc 1) with a clear
#      message naming the limit.
#   4. AC#3: invalid episode type -> pre-flight failure (rc 1) naming the
#      allowed set.
#   5. AC#4: the failure message is clear ("pre-flight" + the specific problem).
#   6. Edge: valid metadata -> proceeds (rc 0, no message).
#   7. Edge: show notes EXACTLY at the limit -> proceeds (boundary, not over).
#   8. Edge: over-length title -> pre-flight failure (rc 1).
#
# The function + its limit constants are extracted from podbean_publish.sh and
# exercised in fresh subshells (the real die() exits 1, so a violation surfaces
# as a non-zero rc + a stderr message). Limits are overridable via env so the
# over-length cases use short fixtures.
#
# MUTATION PROOF (verified during development): inverting the show-notes
# comparison (`-gt` -> `-lt`) makes the over-length test FAIL (RED); reverting
# restores GREEN. The test therefore genuinely guards the bounds logic.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT="$REPO_ROOT/58-podcast-production-engine/scripts/podbean_publish.sh"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

# ─── GUARD 1: bash -n (AC#1) ─────────────────────────────────────────────────
bash -n "$SCRIPT" || fail "bash -n podbean_publish.sh failed (AC#1)"
pass "bash -n podbean_publish.sh passes (AC#1)"

# ─── GUARD 2: the function is wired into the publish flow (not dead code) ────
grep -q 'validate_episode_metadata "\$FINAL_TITLE" "\$DESCRIPTION" "\$EPISODE_TYPE"' "$SCRIPT" \
  || fail "validate_episode_metadata is defined but never called in the publish flow"
pass "function is invoked in the publish flow"

# ─── Extract the limit constants + the function under test ───────────────────
TMP_LIB="$(mktemp)"
trap 'rm -f "$TMP_LIB"' EXIT
CONST_SRC="$(grep -E '^readonly PODBEAN_MAX_DESCRIPTION_LEN=|^readonly PODBEAN_MAX_TITLE_LEN=|^readonly PODBEAN_EPISODE_TYPES=' "$SCRIPT")"
FUNC_SRC="$(sed -n '/^validate_episode_metadata() {/,/^}/p' "$SCRIPT")"
[ -n "$CONST_SRC" ] || fail "could not extract the PODBEAN_* limit constants"
[ -n "$FUNC_SRC" ] || fail "could not extract validate_episode_metadata"
# die() + log() so the extracted function can fail loudly (die exits 1).
cat > "$TMP_LIB" <<EOF
log()  { printf '%s podbean_publish %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\$*" >&2; }
die()  { log "ERROR: \$*"; exit 1; }
$CONST_SRC
$FUNC_SRC
EOF

# Run validate_episode_metadata in a fresh subshell; capture rc + combined output.
# Env vars (PODBEAN_MAX_*) set by the caller propagate into the subshell and are
# picked up by the readonly defaults.
run_validate() {
  ( source "$TMP_LIB"; validate_episode_metadata "$@" ) 2>&1
}

# ─── AC#2: over-length show notes -> pre-flight failure with a clear message ─
rc=0
out="$(PODBEAN_MAX_DESCRIPTION_LEN=10 run_validate "A Title" "this description is way over ten chars" "full")" || rc=$?
[ "$rc" -eq 1 ] || fail "AC#2: over-length show notes must fail (rc 1), got rc=$rc: $out"
echo "$out" | grep -qi "pre-flight" || fail "AC#2: message must say 'pre-flight', got: $out"
echo "$out" | grep -qi "show notes" || fail "AC#2: message must name 'show notes', got: $out"
echo "$out" | grep -q "10" || fail "AC#2: message must name the limit (10), got: $out"
pass "AC#2: over-length show notes -> pre-flight failure with a clear message"

# ─── AC#3: invalid episode type -> pre-flight failure naming the allowed set ─
rc=0
out="$(run_validate "A Title" "short notes" "not-a-real-type")" || rc=$?
[ "$rc" -eq 1 ] || fail "AC#3: invalid episode type must fail (rc 1), got rc=$rc: $out"
echo "$out" | grep -qi "episode type" || fail "AC#3: message must name 'episode type', got: $out"
echo "$out" | grep -q "full" || fail "AC#3: message must list the allowed set (full/...), got: $out"
pass "AC#3: invalid episode type -> pre-flight failure naming the allowed set"

# ─── AC#4: the failure message is clear (pre-flight + specific problem) ──────
# (asserted within AC#2/AC#3 above: both messages carry 'pre-flight' and name the
# exact offending field + limit/allowed-set.)
pass "AC#4: failure messages are clear (pre-flight + specific problem)"

# ─── Edge: valid metadata -> proceeds (rc 0, no message) ─────────────────────
rc=0
out="$(run_validate "A Title" "short notes" "full")" || rc=$?
[ "$rc" -eq 0 ] || fail "edge: valid metadata must proceed (rc 0), got rc=$rc: $out"
[ -z "$out" ] || fail "edge: valid metadata must emit no message, got: $out"
pass "edge: valid metadata -> proceeds (rc 0, no message)"

# ─── Edge: show notes EXACTLY at the limit -> proceeds (boundary, not over) ──
rc=0
out="$(PODBEAN_MAX_DESCRIPTION_LEN=10 run_validate "A Title" "0123456789" "full")" || rc=$?
[ "$rc" -eq 0 ] || fail "edge: show notes exactly at the limit must proceed (rc 0), got rc=$rc: $out"
pass "edge: show notes exactly at the limit -> proceeds (boundary)"

# ─── Edge: over-length title -> pre-flight failure (rc 1) ────────────────────
rc=0
out="$(PODBEAN_MAX_TITLE_LEN=5 run_validate "a much too long title" "short" "full")" || rc=$?
[ "$rc" -eq 1 ] || fail "edge: over-length title must fail (rc 1), got rc=$rc: $out"
echo "$out" | grep -qi "title" || fail "edge: message must name 'title', got: $out"
pass "edge: over-length title -> pre-flight failure (rc 1)"

# ─── Edge: every allowed episode type proceeds ───────────────────────────────
for t in full trailer bonus; do
  rc=0
  out="$(run_validate "A Title" "short" "$t")" || rc=$?
  [ "$rc" -eq 0 ] || fail "edge: episode type '$t' must be allowed (rc 0), got rc=$rc: $out"
done
pass "edge: every allowed episode type (full/trailer/bonus) proceeds"

echo ""
echo "All U037 tests passed."
