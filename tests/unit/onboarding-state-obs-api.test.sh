#!/usr/bin/env bash
# tests/unit/onboarding-state-obs-api.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# obs_* onboarding-state API regression lock (v17.0.19).
#
# THE BUG THIS LOCKS: the PRD-2.1 unify (commit 2c798c72) renamed the onboarding
# state-machine + verification-gate implementation from obs_* to oc_* (into
# lib-onboarding-state.sh) and turned scripts/onboarding-state.sh into a thin
# lib-sourcing shim — but the RUNTIME callers were never migrated. update-skills.sh
# seeds via `obs_seed_state` (~line 991) and runs its verification gate guarded by
# `command -v obs_verify_skill` (~line 2019); install.sh's compat-fallback branch
# and resume-onboarding.sh also call the obs_* names. With NO obs_* compatibility
# layer, sourcing the shim defined only oc_*, so on EVERY roll `obs_seed_state`
# printed "command not found" and the internal verification gate silently degraded
# to "verification gate unavailable / file-sync-only". The fix restores the
# self-contained obs_* state-machine + gate in scripts/onboarding-state.sh AND
# makes update-skills.sh source the shim by a resolved absolute path with a
# `command -v obs_seed_state` self-verify guard.
#
# WHAT THIS TEST PROVES (non-vacuously — it first proves the bug still bites the
# oc_-only lib, so the shim assertions are not vacuous):
#   (1) bash -n parses update-skills.sh, scripts/onboarding-state.sh, install.sh.
#   (2) BUG WITNESS: sourcing lib-onboarding-state.sh ALONE does NOT define
#       obs_seed_state (but DOES define the canonical oc_state_seed).
#   (3) FIX: sourcing scripts/onboarding-state.sh DEFINES the full obs_* API
#       (obs_seed_state / obs_verify_skill / obs_gate_summary / obs_set_status /
#        obs_resolve_workspace).
#   (4) FUNCTIONAL: obs_seed_state seeds .onboarding-state.json with the
#       non-archived numbered skills (ARCHIVED excluded), and obs_gate_summary
#       emits the "GATE-HUMAN:" line that update-skills.sh greps for.
#   (5) STATIC WIRING: update-skills.sh sources the shim by resolved absolute path
#       ($_OBS_SHIM from $ONBOARDING_DIR / $_SCRIPT_DIR), guards the seed with
#       `command -v obs_seed_state`, and its verification gate is STILL guarded by
#       `command -v obs_verify_skill` + calls obs_gate_summary (gate unchanged).
#
# Fully hermetic: sourcing runs under its OWN `mktemp -d` sandbox HOME — nothing
# is written under the operator's ~/.openclaw and no real work is performed.
# bash 3.2-safe (macOS system bash). Exit 0 = all pass.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"
SHIM="$REPO_ROOT/scripts/onboarding-state.sh"
LIB="$REPO_ROOT/lib-onboarding-state.sh"
INSTALL="$REPO_ROOT/install.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== onboarding-state-obs-api.test.sh (v17.0.19 obs_* API restore) ==="

for f in "$UPDATE_SKILLS" "$SHIM" "$LIB" "$INSTALL"; do
  [ -f "$f" ] || { echo "  FAIL: missing $f"; exit 1; }
done
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 not on PATH"; exit 1; }

# ── (1) parse ────────────────────────────────────────────────────────────────
bash -n "$UPDATE_SKILLS" 2>/dev/null && pass "update-skills.sh parses (bash -n)" || fail "update-skills.sh bash -n FAILED"
bash -n "$SHIM"          2>/dev/null && pass "scripts/onboarding-state.sh parses (bash -n)" || fail "shim bash -n FAILED"
bash -n "$LIB"           2>/dev/null && pass "lib-onboarding-state.sh parses (bash -n)" || fail "lib bash -n FAILED"
bash -n "$INSTALL"       2>/dev/null && pass "install.sh parses (bash -n)" || fail "install.sh bash -n FAILED"

# ── (2) BUG WITNESS: oc_ lib alone does NOT define obs_seed_state ────────────
witness_home="$(mktemp -d)"
witness_out="$(HOME="$witness_home" bash -c '
  set -uo pipefail
  source "'"$LIB"'" >/dev/null 2>&1
  command -v obs_seed_state >/dev/null 2>&1 && echo "OBS_DEF" || echo "OBS_UNDEF"
  command -v oc_state_seed  >/dev/null 2>&1 && echo "OC_DEF"  || echo "OC_UNDEF"
' 2>/dev/null)"
rm -rf "$witness_home"
case "$witness_out" in
  *OBS_UNDEF*) pass "bug witness: lib-onboarding-state.sh ALONE does NOT define obs_seed_state" ;;
  *)          fail "bug witness vacuous: lib ALONE unexpectedly defines obs_seed_state (assertions below would be meaningless)" ;;
esac
case "$witness_out" in
  *OC_DEF*) pass "canonical oc_state_seed IS defined by the lib" ;;
  *)        fail "canonical oc_state_seed NOT defined by the lib" ;;
esac

# ── (3)+(4) FIX: shim defines the full obs_* API and it FUNCTIONS ────────────
fix_home="$(mktemp -d)"
src_tree="$fix_home/src"
mkdir -p "$src_tree/23-ai-workforce-blueprint" \
         "$src_tree/38-conversational-ai-system" \
         "$src_tree/99-ARCHIVED-legacy" \
         "$src_tree/not-a-numbered-skill"
fix_out="$(HOME="$fix_home" SKILLS_DIR="$src_tree" bash -c '
  set -uo pipefail
  source "'"$SHIM"'" >/dev/null 2>&1
  for fn in obs_seed_state obs_verify_skill obs_gate_summary obs_set_status obs_resolve_workspace obs_get_status; do
    command -v "$fn" >/dev/null 2>&1 && echo "DEF:$fn" || echo "UNDEF:$fn"
  done
  obs_seed_state "v17.0.19" "'"$src_tree"'" >/dev/null 2>&1
  sf="$HOME/.openclaw/workspace/.onboarding-state.json"
  [ -f "$sf" ] && echo "STATE_FILE_OK" || echo "STATE_FILE_MISSING"
  python3 - "$sf" <<PYEOF
import json,sys
try:
    st=json.load(open(sys.argv[1]))
except Exception:
    print("SKILLS:ERR"); sys.exit(0)
ks=sorted(st.get("skills",{}).keys())
print("SKILLS:"+",".join(ks))
PYEOF
  obs_gate_summary "'"$src_tree"'" 2>/dev/null || true
' 2>/dev/null)"
rm -rf "$fix_home"

for fn in obs_seed_state obs_verify_skill obs_gate_summary obs_set_status obs_resolve_workspace obs_get_status; do
  case "$fix_out" in
    *"DEF:$fn"*) pass "shim defines $fn" ;;
    *)           fail "shim does NOT define $fn" ;;
  esac
done
case "$fix_out" in
  *STATE_FILE_OK*) pass "obs_seed_state wrote .onboarding-state.json" ;;
  *)               fail "obs_seed_state did NOT write the state file" ;;
esac
# The two non-archived numbered skills are seeded; ARCHIVED + non-numbered excluded.
case "$fix_out" in
  *"SKILLS:23-ai-workforce-blueprint,38-conversational-ai-system"*)
    pass "obs_seed_state discovered exactly the non-archived numbered skills (ARCHIVED excluded)" ;;
  *)
    fail "obs_seed_state skill discovery wrong — got: $(printf '%s' "$fix_out" | grep -o 'SKILLS:[^ ]*')" ;;
esac
case "$fix_out" in
  *"GATE-HUMAN:"*) pass "obs_gate_summary emits the GATE-HUMAN: line update-skills.sh greps for" ;;
  *)               fail "obs_gate_summary did NOT emit a GATE-HUMAN: line" ;;
esac

# ── (5) STATIC WIRING in update-skills.sh ───────────────────────────────────
if grep -qE 'source[[:space:]]+"\$_OBS_SHIM"' "$UPDATE_SKILLS" \
   && grep -qE '_OBS_SHIM=' "$UPDATE_SKILLS" \
   && grep -qE '\$ONBOARDING_DIR/scripts/onboarding-state\.sh' "$UPDATE_SKILLS" \
   && grep -qE '\$\{_SCRIPT_DIR:-\}/scripts/onboarding-state\.sh' "$UPDATE_SKILLS"; then
  pass "update-skills.sh sources the shim by resolved absolute path (pulled-tree + script-dir fallback)"
else
  fail "update-skills.sh does NOT robustly resolve+source the shim by absolute path"
fi

if grep -qE 'command -v obs_seed_state >/dev/null 2>&1' "$UPDATE_SKILLS"; then
  pass "update-skills.sh self-verifies obs_seed_state is defined before invoking it"
else
  fail "update-skills.sh does NOT guard the obs_seed_state call with command -v"
fi

if grep -qE 'command -v obs_verify_skill >/dev/null 2>&1' "$UPDATE_SKILLS" \
   && grep -qE 'obs_gate_summary "\$SKILLS_DIR"' "$UPDATE_SKILLS"; then
  pass "verification gate is STILL guarded by obs_verify_skill + calls obs_gate_summary (gate unchanged, now reachable)"
else
  fail "verification gate wiring changed/absent (obs_verify_skill / obs_gate_summary)"
fi

echo ""
echo "=== onboarding-state-obs-api.test.sh: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
