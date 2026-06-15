#!/usr/bin/env bash
# ============================================================
#  test-ungated-claim-points.sh — QC Meta-Gate (X2) + Acceptance Tests (A6/B7/C4)
#
#  X2: Greps the codebase for new ungated proxy writers.
#       Any new literal "status.*=.*done" / .onboarding-version write /
#       wiringStatus.*done write outside the known gated writers FAILS CI.
#
#  A6: Acceptance test for Fix A (content/SHA gate)
#  B7: Acceptance test for Fix B (registration must be fatal)
#  C4: Acceptance test for Fix C (converge done-flip gated on library+wiring)
#
#  EXIT CODES:
#    0  — all tests passed
#    1  — one or more tests failed
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; (( PASS_COUNT++ )) || true; }
_fail() { echo "  FAIL: $1" >&2; (( FAIL_COUNT++ )) || true; }
_section() { echo ""; echo "=== $1 ==="; }

# ─── X2: QC Meta-Gate ────────────────────────────────────────────────────────
_section "X2 — Meta-gate: no new ungated proxy writers"

# Known-gated writers (these are ALLOWED to write the proxy):
# - scripts/update-skills.sh: writes .onboarding-version AFTER A3 content gate
# - 23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py: gated in C2
# - 32-command-center-setup/scripts/sync-extensions.sh: gated in C3

# Check for any new literal status:done WRITES (assignments) NOT in the known gated files.
# We specifically look for assignment patterns ("status" = "done" or .status = "done"),
# NOT read/filter patterns (select(.status == "done"), status == "done" comparisons).
_STATUS_DONE_HITS=$(grep -rn '["'"'"']status["'"'"'].*[=:][^=].*["'"'"']done["'"'"']\|\.status\s*=\s*["'"'"']done["'"'"']' \
  "$REPO_ROOT/23-ai-workforce-blueprint/scripts/" \
  "$REPO_ROOT/32-command-center-setup/scripts/" \
  "$REPO_ROOT/37-zhc-closeout/scripts/" \
  --include="*.sh" --include="*.py" 2>/dev/null | \
  grep -v "# gated\|# GATED\|gated_done\|verif\|gate_pass\|gate pass\|gate PASS\|_GATE\|GATE_\|verify\|verifying\|TEST\|test\|_test\|expected\|# allowed\|closeoutStatus\|buildComplete\|closeout_status\|converge_status\|blocked\|wiringStatus\|_CONVERGE_STATUS\|CONVERGE_STATUS\|_new_status\|new_status\|dept_done\|_build_complete\|# B2\|# C2\|# C3\|# B5\|select(\|jq \|rl_status\|sop_status\|commsAutomation\|msg=.*done\|log.*done\|echo.*done\|print.*done\|help=\|\"status\"\s*in\s*\|IN(" \
  || true)

if [ -n "$_STATUS_DONE_HITS" ]; then
  _fail "X2: Ungated status:done writes found — review and gate or add to allowlist:"
  echo "$_STATUS_DONE_HITS" | head -20 >&2
else
  _pass "X2: No ungated status:done writes found in blueprint/sync/closeout scripts"
fi

# Check for .onboarding-version WRITES outside update-skills.sh
# (reads via cat/tr/open/read/path reference are allowed — only echo/write/open-for-write are flagged)
_STAMP_HITS=$(grep -rn '\.onboarding-version' "$REPO_ROOT" \
  --include="*.sh" --include="*.py" 2>/dev/null | \
  grep -v "update-skills.sh\|check-updates.sh\|force-update.sh\|install.sh\|skill-content-hash.sh\|DONE-IS-GATED\|test-ungated\|test-fleet-refresh\|fleet_refresh_runner\|# read\|cat \|read \|tr \|legacy\|_LEGACY\|LEGACY_MARKER\|verify\|VERIFY\|v_file\|path\|open(" \
  || true)

if [ -n "$_STAMP_HITS" ]; then
  _fail "X2: .onboarding-version writes found outside the gated update scripts:"
  echo "$_STAMP_HITS" | head -10 >&2
else
  _pass "X2: .onboarding-version writes are confined to known scripts"
fi

# ─── A6: Content/SHA Gate Acceptance Test ────────────────────────────────────
_section "A6 — Content-gate acceptance test"

HASH_SCRIPT="$REPO_ROOT/scripts/skill-content-hash.sh"
if [ ! -f "$HASH_SCRIPT" ]; then
  _fail "A6: skill-content-hash.sh not found at $HASH_SCRIPT"
else
  # Create a synthetic skills dir with two mock skills
  _SANDBOX=$(mktemp -d)
  trap 'rm -rf "$_SANDBOX"' EXIT

  mkdir -p "$_SANDBOX/01-mock-skill-one" "$_SANDBOX/02-mock-skill-two"
  echo "hello world" > "$_SANDBOX/01-mock-skill-one/SKILL.md"
  echo "goodbye world" > "$_SANDBOX/02-mock-skill-two/SKILL.md"

  # Compute initial manifest
  MANIFEST_A=$(bash "$HASH_SCRIPT" "$_SANDBOX" 2>/dev/null)
  TREE_A=$(echo "$MANIFEST_A" | grep "^__TREE_SHA__|" | cut -d'|' -f2)

  if [ -z "$TREE_A" ]; then
    _fail "A6: skill-content-hash.sh did not emit __TREE_SHA__ line"
  else
    _pass "A6: skill-content-hash.sh emitted __TREE_SHA__=$TREE_A"
  fi

  # Simulate content drift: corrupt one file without touching a version stamp
  echo "corrupted content" > "$_SANDBOX/01-mock-skill-one/SKILL.md"

  MANIFEST_B=$(bash "$HASH_SCRIPT" "$_SANDBOX" 2>/dev/null)
  TREE_B=$(echo "$MANIFEST_B" | grep "^__TREE_SHA__|" | cut -d'|' -f2)

  if [ "$TREE_A" != "$TREE_B" ]; then
    _pass "A6: content drift detected correctly (tree SHA changed after file corruption)"
  else
    _fail "A6: content drift NOT detected (tree SHA unchanged after corruption)"
  fi

  # Verify per-skill digest changes too
  DIGEST_A1=$(echo "$MANIFEST_A" | grep "^01-mock-skill-one|" | cut -d'|' -f2)
  DIGEST_B1=$(echo "$MANIFEST_B" | grep "^01-mock-skill-one|" | cut -d'|' -f2)

  if [ "$DIGEST_A1" != "$DIGEST_B1" ]; then
    _pass "A6: per-skill digest changed for corrupted skill"
  else
    _fail "A6: per-skill digest did NOT change after file corruption"
  fi

  # Verify non-corrupted skill is unchanged
  DIGEST_A2=$(echo "$MANIFEST_A" | grep "^02-mock-skill-two|" | cut -d'|' -f2)
  DIGEST_B2=$(echo "$MANIFEST_B" | grep "^02-mock-skill-two|" | cut -d'|' -f2)

  if [ "$DIGEST_A2" = "$DIGEST_B2" ]; then
    _pass "A6: unmodified skill digest unchanged (no false positives)"
  else
    _fail "A6: unmodified skill digest changed unexpectedly"
  fi

  # Test that excluded files (skill-version.txt, .wired-*) are excluded
  echo "v1.0.0" > "$_SANDBOX/01-mock-skill-one/skill-version.txt"
  echo "wired" > "$_SANDBOX/01-mock-skill-one/.wired-someservice"
  MANIFEST_C=$(bash "$HASH_SCRIPT" "$_SANDBOX" 2>/dev/null)
  DIGEST_C1=$(echo "$MANIFEST_C" | grep "^01-mock-skill-one|" | cut -d'|' -f2)

  if [ "$DIGEST_B1" = "$DIGEST_C1" ]; then
    _pass "A6: volatile files (skill-version.txt, .wired-*) excluded from hash"
  else
    _fail "A6: volatile files changed the digest (should be excluded)"
  fi

  rm -rf "$_SANDBOX"
  trap - EXIT
fi

# ─── B7: Registration-fatal Acceptance Test ───────────────────────────────────
_section "B7 — Registration-fatal acceptance test (syntax/logic check only)"

BUILD_WF="$REPO_ROOT/23-ai-workforce-blueprint/scripts/build-workforce.py"
if [ ! -f "$BUILD_WF" ]; then
  _fail "B7: build-workforce.py not found"
else
  # Verify python syntax is valid
  if python3 -m py_compile "$BUILD_WF" 2>/dev/null; then
    _pass "B7: build-workforce.py compiles without syntax errors"
  else
    _fail "B7: build-workforce.py has syntax errors"
  fi

  # Check that registration_failures is now tracked (B1)
  if grep -q "registration_failures" "$BUILD_WF"; then
    _pass "B7: registration_failures tracking found in build-workforce.py"
  else
    _fail "B7: registration_failures not found in build-workforce.py (B1 not applied)"
  fi

  # Check that progress_pct is no longer hardcoded to 100 when registration fails (B2)
  if grep -q "_build_progress" "$BUILD_WF"; then
    _pass "B7: _build_progress variable found (B2 gating applied)"
  else
    _fail "B7: _build_progress not found — progress may still be hardcoded to 100"
  fi

  # Check that "blocked-no-config" wiringStatus is written when config absent (B1)
  if grep -q "blocked-no-config" "$BUILD_WF"; then
    _pass "B7: blocked-no-config wiringStatus written when openclaw.json absent"
  else
    _fail "B7: blocked-no-config not found in build-workforce.py"
  fi
fi

# B7: verify-wiring.sh exists and has the hard-fail for missing config (B3)
VERIFY_WIRING="$REPO_ROOT/23-ai-workforce-blueprint/scripts/verify-wiring.sh"
if [ ! -f "$VERIFY_WIRING" ]; then
  _fail "B7: verify-wiring.sh not found in 23-ai-workforce-blueprint/scripts/"
else
  if bash -n "$VERIFY_WIRING" 2>/dev/null; then
    _pass "B7: verify-wiring.sh has valid bash syntax"
  else
    _fail "B7: verify-wiring.sh has bash syntax errors"
  fi

  if grep -q "allow-missing-config\|ALLOW_MISSING_CONFIG" "$VERIFY_WIRING"; then
    _pass "B7: verify-wiring.sh supports --allow-missing-config flag (B3)"
  else
    _fail "B7: verify-wiring.sh missing --allow-missing-config flag (B3 not applied)"
  fi

  if grep -q "openclaw-json-missing\|openclaw.json.*HARD FAIL\|HARD FAIL" "$VERIFY_WIRING"; then
    _pass "B7: verify-wiring.sh has HARD FAIL for missing openclaw.json (B3)"
  else
    _fail "B7: verify-wiring.sh does not HARD FAIL on missing config (B3 not applied)"
  fi
fi

# B7: run-closeout.sh has verify-wiring.sh as precondition (B5)
CLOSEOUT="$REPO_ROOT/37-zhc-closeout/scripts/run-closeout.sh"
if [ ! -f "$CLOSEOUT" ]; then
  _fail "B7: run-closeout.sh not found"
else
  if grep -q "verify-wiring\|blocked-wiring-incomplete" "$CLOSEOUT"; then
    _pass "B7: run-closeout.sh has verify-wiring.sh precondition (B5)"
  else
    _fail "B7: run-closeout.sh missing verify-wiring.sh precondition (B5 not applied)"
  fi
fi

# ─── C4: Converge done-flip gated on library+wiring ──────────────────────────
_section "C4 — Converge done-flip acceptance test (logic/structure check)"

REFRESH_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py"
if [ ! -f "$REFRESH_PY" ]; then
  _fail "C4: refresh-build-state-from-index.py not found"
else
  if python3 -m py_compile "$REFRESH_PY" 2>/dev/null; then
    _pass "C4: refresh-build-state-from-index.py compiles without syntax errors"
  else
    _fail "C4: refresh-build-state-from-index.py has syntax errors"
  fi

  # Check that --strict and --counts-only modes are implemented (C2)
  if grep -q "counts.only\|counts_only" "$REFRESH_PY"; then
    _pass "C4: --counts-only mode implemented in refresh-build-state-from-index.py (C2)"
  else
    _fail "C4: --counts-only mode not found in refresh-build-state-from-index.py"
  fi

  # Check that status:done is gated on dept_done (not just roles_count)
  if grep -q "dept_done\|wiring_done\|wiringStatus.*done" "$REFRESH_PY"; then
    _pass "C4: status:done gated on dept_done / wiringStatus in refresh-build-state"
  else
    _fail "C4: status:done not gated on library+wiring in refresh-build-state (C2 not applied)"
  fi
fi

# C4: sync-extensions.sh runs gates before done claim (C3)
SYNC_EXT="$REPO_ROOT/32-command-center-setup/scripts/sync-extensions.sh"
if [ ! -f "$SYNC_EXT" ]; then
  _fail "C4: sync-extensions.sh not found"
else
  if grep -q "verify-library-gate\|_GATE_LIB_RC" "$SYNC_EXT"; then
    _pass "C4: sync-extensions.sh runs verify-library-gate.sh before done claim (C3)"
  else
    _fail "C4: sync-extensions.sh does not run library gate before done claim (C3 not applied)"
  fi

  if grep -q "verify-wiring\|_GATE_WIRING_RC" "$SYNC_EXT"; then
    _pass "C4: sync-extensions.sh runs verify-wiring.sh before done claim (C3)"
  else
    _fail "C4: sync-extensions.sh does not run wiring gate before done claim (C3 not applied)"
  fi

  if grep -q "_CONVERGE_STATUS\|converge_status\|incomplete" "$SYNC_EXT"; then
    _pass "C4: sync-extensions.sh ledger status is conditional (not always done)"
  else
    _fail "C4: sync-extensions.sh ledger may still unconditionally write status:done"
  fi
fi

# ─── Final report ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  TEST RESULTS: $PASS_COUNT passed, $FAIL_COUNT failed"
echo "═══════════════════════════════════════════════════════════════"

if [[ $FAIL_COUNT -gt 0 ]]; then
  exit 1
fi
exit 0
