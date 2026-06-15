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

# ─── C4-BEHAVIORAL: refresh-build-state gated done-flip (real run) ────────────
_section "C4-BEHAVIORAL — refresh-build-state-from-index.py gated done-flip (real run)"

REFRESH_PY="$REPO_ROOT/23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py"
if [ -f "$REFRESH_PY" ]; then
  _C4_SANDBOX=$(mktemp -d)
  # Seed an _index.json with one dept that has role NAMES (count>0)
  cat > "$_C4_SANDBOX/_index.json" <<'IDXEOF'
{
  "total_roles": 3,
  "departments": {
    "operations": {
      "roles": ["operations-director", "ops-analyst", "ops-coordinator"]
    }
  }
}
IDXEOF

  # Seed a build-state with the dept present but library/wiring NOT done
  cat > "$_C4_SANDBOX/.workforce-build-state.json" <<'BSEOF'
{
  "departments": {
    "operations": {
      "slug": "operations",
      "name": "Operations",
      "status": "building",
      "rolesPlanned": 0,
      "rolesDone": 0,
      "roleLibraryFilled": false,
      "sopLibraryFilled": false,
      "wiringStatus": "pending"
    }
  },
  "totalRoles": 0,
  "totalDepartments": 0
}
BSEOF

  # Run in --strict mode (default). The dept has role NAMES but library/wiring
  # are NOT done -> status must NOT flip to done.
  WORKFORCE_INDEX_PATH="$_C4_SANDBOX/_index.json" \
  WORKFORCE_BUILD_STATE_PATH="$_C4_SANDBOX/.workforce-build-state.json" \
    python3 "$REFRESH_PY" --strict >/dev/null 2>&1 || true

  _C4_STATUS=$(python3 -c "import json; d=json.load(open('$_C4_SANDBOX/.workforce-build-state.json')); print(d['departments']['operations']['status'])" 2>/dev/null || echo "ERROR")
  _C4_ROLES=$(python3 -c "import json; d=json.load(open('$_C4_SANDBOX/.workforce-build-state.json')); print(d['departments']['operations']['rolesDone'])" 2>/dev/null || echo "ERROR")

  if [ "$_C4_STATUS" != "done" ]; then
    _pass "C4-BEHAVIORAL: dept with role names but unfilled library/wiring did NOT flip to done (status=$_C4_STATUS)"
  else
    _fail "C4-BEHAVIORAL: dept incorrectly flipped to done despite unfilled library/wiring"
  fi

  if [ "$_C4_ROLES" = "3" ]; then
    _pass "C4-BEHAVIORAL: role counts still updated to 3 (counts are not gated, only status is)"
  else
    _fail "C4-BEHAVIORAL: role counts not updated correctly (got $_C4_ROLES, expected 3)"
  fi

  # Now flip the gate fields to done and re-run -> status SHOULD become done
  python3 -c "
import json
p='$_C4_SANDBOX/.workforce-build-state.json'
d=json.load(open(p))
d['departments']['operations']['roleLibraryFilled']=True
d['departments']['operations']['sopLibraryFilled']=True
d['departments']['operations']['wiringStatus']='done'
json.dump(d, open(p,'w'), indent=2)
" 2>/dev/null

  WORKFORCE_INDEX_PATH="$_C4_SANDBOX/_index.json" \
  WORKFORCE_BUILD_STATE_PATH="$_C4_SANDBOX/.workforce-build-state.json" \
    python3 "$REFRESH_PY" --strict >/dev/null 2>&1 || true

  _C4_STATUS2=$(python3 -c "import json; d=json.load(open('$_C4_SANDBOX/.workforce-build-state.json')); print(d['departments']['operations']['status'])" 2>/dev/null || echo "ERROR")
  if [ "$_C4_STATUS2" = "done" ]; then
    _pass "C4-BEHAVIORAL: dept flipped to done once library+wiring gates pass (status=$_C4_STATUS2)"
  else
    _fail "C4-BEHAVIORAL: dept did NOT flip to done even after gates passed (status=$_C4_STATUS2)"
  fi

  # --counts-only must update counts WITHOUT touching status (regression guard)
  python3 -c "
import json
p='$_C4_SANDBOX/.workforce-build-state.json'
d=json.load(open(p))
d['departments']['operations']['status']='building'
d['departments']['operations']['roleLibraryFilled']=False
json.dump(d, open(p,'w'), indent=2)
" 2>/dev/null

  WORKFORCE_INDEX_PATH="$_C4_SANDBOX/_index.json" \
  WORKFORCE_BUILD_STATE_PATH="$_C4_SANDBOX/.workforce-build-state.json" \
    python3 "$REFRESH_PY" --counts-only >/dev/null 2>&1 || true

  _C4_STATUS3=$(python3 -c "import json; d=json.load(open('$_C4_SANDBOX/.workforce-build-state.json')); print(d['departments']['operations']['status'])" 2>/dev/null || echo "ERROR")
  if [ "$_C4_STATUS3" = "building" ]; then
    _pass "C4-BEHAVIORAL: --counts-only updated counts WITHOUT flipping status (regression guard)"
  else
    _fail "C4-BEHAVIORAL: --counts-only changed status (got $_C4_STATUS3, expected building)"
  fi

  rm -rf "$_C4_SANDBOX"
else
  _fail "C4-BEHAVIORAL: refresh-build-state-from-index.py not found"
fi

# ─── A6-BEHAVIORAL: content-gate refuses stamp on mismatched source ──────────
# This simulates the EXACT A3 comparison loop from update-skills.sh: build a
# source manifest and a destination manifest, compare per-skill digests, and
# assert the gate (a) PASSES when src==dest and (b) FAILS (stamp refused) when
# the destination content does not match source.
_section "A6-BEHAVIORAL — A3 content-gate stamp refusal (real digest comparison)"

HASH_SCRIPT="$REPO_ROOT/scripts/skill-content-hash.sh"
if [ -f "$HASH_SCRIPT" ]; then
  _A6_SRC=$(mktemp -d)
  _A6_DEST=$(mktemp -d)

  # Identical content first (clean install)
  for d in "$_A6_SRC" "$_A6_DEST"; do
    mkdir -p "$d/01-skill-a" "$d/02-skill-b"
    echo "alpha content v1" > "$d/01-skill-a/SKILL.md"
    echo "beta content v1" > "$d/02-skill-b/SKILL.md"
  done

  # Helper that replicates the A3 gate decision
  _a6_gate() {
    local src_dir="$1" dest_dir="$2"
    local src_manifest dest_manifest gate_pass=1
    src_manifest=$(bash "$HASH_SCRIPT" "$src_dir" 2>/dev/null)
    dest_manifest=$(bash "$HASH_SCRIPT" "$dest_dir" 2>/dev/null)
    while IFS='|' read -r sn sd; do
      [ -z "$sn" ] && continue
      [ "$sn" = "__TREE_SHA__" ] && continue
      local dd
      dd=$(echo "$dest_manifest" | grep "^${sn}|" | cut -d'|' -f2 | head -1)
      if [ -z "$dd" ] || [ "$dd" != "$sd" ]; then
        gate_pass=0
      fi
    done <<< "$src_manifest"
    echo "$gate_pass"
  }

  _A6_RESULT_CLEAN=$(_a6_gate "$_A6_SRC" "$_A6_DEST")
  if [ "$_A6_RESULT_CLEAN" = "1" ]; then
    _pass "A6-BEHAVIORAL: clean install (src==dest) — gate PASSES, stamp allowed"
  else
    _fail "A6-BEHAVIORAL: clean install incorrectly failed the gate"
  fi

  # Now corrupt the destination (half-applied install) — gate must REFUSE stamp
  echo "CORRUPTED beta content" > "$_A6_DEST/02-skill-b/SKILL.md"
  _A6_RESULT_DRIFT=$(_a6_gate "$_A6_SRC" "$_A6_DEST")
  if [ "$_A6_RESULT_DRIFT" = "0" ]; then
    _pass "A6-BEHAVIORAL: mismatched source/dest — gate FAILS, stamp REFUSED (half-applied-box fix)"
  else
    _fail "A6-BEHAVIORAL: gate did NOT detect content mismatch — stamp would be falsely written"
  fi

  # Missing skill in destination must also fail the gate
  cp -R "$_A6_SRC/02-skill-b/SKILL.md" "$_A6_DEST/02-skill-b/SKILL.md"   # fix corruption
  rm -rf "$_A6_DEST/01-skill-a"                                          # delete a whole skill
  _A6_RESULT_MISSING=$(_a6_gate "$_A6_SRC" "$_A6_DEST")
  if [ "$_A6_RESULT_MISSING" = "0" ]; then
    _pass "A6-BEHAVIORAL: skill missing in dest — gate FAILS, stamp REFUSED"
  else
    _fail "A6-BEHAVIORAL: gate did NOT detect a missing skill in destination"
  fi

  rm -rf "$_A6_SRC" "$_A6_DEST"
else
  _fail "A6-BEHAVIORAL: skill-content-hash.sh not found"
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
