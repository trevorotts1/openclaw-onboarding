#!/usr/bin/env bash
# tests/unit/cc-currency-untracked-is-not-dirty.test.sh
# ---------------------------------------------------------------------------
# Proves the fix for a live finding on a client Mac: update-skills.sh printed
#
#   ✗ [CC CURRENCY] state=dirty head=bc06e9c0 — Command Center has UNCOMMITTED
#     changes, so it cannot fast-forward and will NOT be refreshed
#
# on a checkout whose `git status --porcelain` showed ZERO modified tracked
# files — only ten untracked `??` entries (old DB safety copies, a stray
# script, a scratch markdown). The Command Center's own update.sh pulled that
# same tree five times the same day.
#
# THE DEFECT. Three separate Command Center gates in update-skills.sh each
# spelled "dirty" as `[ -n "$(git status --porcelain)" ]`. Porcelain lists
# untracked files too, so any box carrying stray `??` files never received a
# Command Center refresh through this updater.
#
# THE FIX. Each gate filters `^??`, so dirty means modified-or-staged TRACKED
# files only and untracked files are reported as an INFO count. The refusal for
# genuinely modified tracked files is unchanged — uncommitted client work is
# load-bearing.
#
# WHY THE RULE IS INLINE AND NOT A FUNCTION. All three gates sit inside
# marker-delimited blocks that scripts/test-updater-traps-1-and-3.sh and
# tests/unit/content-recheck-convergence-probes.test.sh extract VERBATIM and
# source STANDALONE. A call to a top-level helper is an undefined command
# there, which evaluates to "clean" and lets the gate through silently. That
# was measured: routing them through a helper failed 13 assertions in one suite
# and 5 in the other. So the rule is written out at each gate, and THIS suite
# is what keeps the three copies honest.
#
# METHOD. It does NOT retype the rule: it LIFTS the expression out of
# update-skills.sh's DIRTY-CHECKOUT GUARD and runs that against real `git init`
# fixtures, so the assertions judge the shipped rule and real porcelain output
# rather than a mocked string. Section 7 then asserts all three gates carry it.
# A PRE-FIX control reruns the old one-line definition on the same fixture and
# must reproduce the live incident.
#
# FULLY OFFLINE. No remote, no network, no box.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $*"; }

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── The canonical rule, LIFTED FROM update-skills.sh, not retyped ───────────
# All three gates spell it inline (they sit in blocks other suites extract and
# source standalone, where a top-level helper would be an undefined command).
# So this suite lifts the expression out of the DIRTY-CHECKOUT GUARD and runs
# THAT against real fixtures — if the shipped rule changes, this runs the new
# one and the fixture assertions below are what judge it.
CANON_TRACKED="$(grep -oE 'git -C "\$_CC_DIR" status --porcelain 2>/dev/null \| grep -v .\^\?\?. \|\| true' "$UPDATER" | head -n1)"
[ -n "$CANON_TRACKED" ] || {
  echo "FATAL: could not lift the tracked-changes rule out of update-skills.sh's DIRTY-CHECKOUT GUARD"
  echo "       (marker drift, or the gate stopped filtering '^??')"; exit 2; }

cc_tracked_changes() { _CC_DIR="$1"; eval "$CANON_TRACKED"; }
cc_untracked_count() {
  local _n
  _n="$(git -C "$1" status --porcelain 2>/dev/null | grep -c '^??' || true)"
  printf '%s' "${_n:-0}" | tr -d '[:space:]'
}

# ── Fixture: a real git repo with one committed file ────────────────────────
mkfixture() {
  local d="$1"
  mkdir -p "$d"
  git -C "$d" init --quiet
  git -C "$d" config user.email t@example.com
  git -C "$d" config user.name  T
  printf 'v1\n' > "$d/tracked.txt"
  git -C "$d" add tracked.txt
  git -C "$d" -c commit.gpgsign=false commit --quiet -m init
}

echo "== (1) untracked-only tree is NOT dirty: refresh proceeds =="
U="$WORK/untracked"; mkfixture "$U"
# the ten strays the client box actually carried
for f in mission-control.db.bak-1 mission-control.db.bak-2 mission-control.db.bak-3 \
         mission-control.db.bak-4 mission-control.db.bak-5 stray-script.sh \
         NOTES.md tmp1 tmp2 tmp3; do printf 'x\n' > "$U/$f"; done

if [ -z "$(cc_tracked_changes "$U")" ]; then
  ok "(1) cc_tracked_changes is EMPTY on a tree with 10 untracked files — the gate sees a clean checkout"
else
  bad "(1) cc_tracked_changes reported changes on an untracked-only tree: $(cc_tracked_changes "$U")"
fi
if [ "$(cc_untracked_count "$U")" = "10" ]; then
  ok "(1) cc_untracked_count reports 10 — surfaced as INFO, not a reason to refuse"
else
  bad "(1) cc_untracked_count = '$(cc_untracked_count "$U")', expected 10"
fi

echo "== (2) modified TRACKED file IS dirty: refresh skipped =="
M="$WORK/modified"; mkfixture "$M"
printf 'v2-local-edit\n' > "$M/tracked.txt"
if [ -n "$(cc_tracked_changes "$M")" ]; then
  ok "(2) cc_tracked_changes is NON-EMPTY on a modified tracked file — the refusal still fires"
else
  bad "(2) a modified tracked file was NOT reported dirty — the protection was lost"
fi
if [ "$(cc_untracked_count "$M")" = "0" ]; then
  ok "(2) cc_untracked_count = 0 on that tree, so the INFO line stays silent"
else
  bad "(2) cc_untracked_count = '$(cc_untracked_count "$M")', expected 0"
fi

echo "== (3) STAGED tracked file is dirty too =="
S="$WORK/staged"; mkfixture "$S"
printf 'v2-staged\n' > "$S/tracked.txt"
git -C "$S" add tracked.txt
if [ -n "$(cc_tracked_changes "$S")" ]; then
  ok "(3) a staged-but-uncommitted tracked change is dirty"
else
  bad "(3) a staged tracked change was NOT reported dirty"
fi

echo "== (4) genuinely clean tree =="
C="$WORK/clean"; mkfixture "$C"
if [ -z "$(cc_tracked_changes "$C")" ] && [ "$(cc_untracked_count "$C")" = "0" ]; then
  ok "(4) clean tree: no tracked changes, no untracked files"
else
  bad "(4) clean tree misreported"
fi

echo "== (5) mixed tree: untracked files never mask a real tracked edit =="
X="$WORK/mixed"; mkfixture "$X"
printf 'v2\n' > "$X/tracked.txt"; printf 'x\n' > "$X/stray.tmp"
if [ -n "$(cc_tracked_changes "$X")" ] && [ "$(cc_untracked_count "$X")" = "1" ]; then
  ok "(5) tracked edit still refuses while the untracked file is counted separately"
else
  bad "(5) mixed tree misreported: tracked='$(cc_tracked_changes "$X")' untracked='$(cc_untracked_count "$X")'"
fi

echo "== (6) PRE-FIX CONTROL: the old definition reproduces the live incident =="
# The exact one-liner all three gates used before this fix.
prefix_dirty() { git -C "$1" status --porcelain 2>/dev/null || true; }
if [ -n "$(prefix_dirty "$U")" ]; then
  ok "(6) NEGATIVE CONTROL CONFIRMED: plain porcelain calls the untracked-only tree DIRTY — the live incident, which test (1) proves the fix no longer does"
else
  bad "(6) NEGATIVE CONTROL FAILED TO REPRODUCE: plain porcelain saw the untracked-only tree as clean — this test would not have caught the incident"
fi
if [ -n "$(prefix_dirty "$M")" ]; then
  ok "(6) old and new definitions still AGREE on a modified tracked file — the fix narrowed only the untracked case"
else
  bad "(6) pre-fix definition did not flag a modified tracked file — fixture is wrong"
fi

echo "== (7) every Command Center gate uses the tracked-only definition =="
# Every gate lives in a block some suite extracts and sources standalone, so
# each must carry the rule INLINE. Assert all three, by variable name.
for v in _dirty:_d _fast_dirty:_fast_p _CC_DIRTY_STATUS:_CC_DIR; do
  _var="${v%%:*}"; _dirvar="${v##*:}"
  if grep -qF "${_var}=\"\$(git -C \"\$${_dirvar}\" status --porcelain 2>/dev/null | grep -v '^??' || true)\"" "$UPDATER"; then
    ok "(7) gate \$${_var} carries the canonical tracked-only rule inline"
  else
    bad "(7) gate \$${_var} does not carry the canonical inline rule (helper call or raw porcelain back?)"
  fi
done
# A top-level helper would be an undefined command inside those extracted
# blocks, which evaluates to "clean" and lets the gate through silently.
if grep -qE '(_dirty|_fast_dirty|_CC_DIRTY_STATUS)="\$\(cc_tracked_changes' "$UPDATER"; then
  bad "(7) a gate calls a top-level helper — undefined when its block is sourced standalone"
else
  ok "(7) no gate depends on a top-level helper"
fi
# No Command Center gate may assign UNFILTERED porcelain.
if grep -E '(_dirty|_fast_dirty|_CC_DIRTY_STATUS)="\$\(git -C [^)]*status --porcelain[^)]*\)"' "$UPDATER" \
     | grep -qv 'grep -v'; then
  bad "(7) a Command Center gate still assigns UNFILTERED porcelain output"
else
  ok "(7) no Command Center gate assigns unfiltered porcelain any more"
fi

echo "== (8) both operator-facing messages say TRACKED =="
if grep -qF 'Command Center has UNCOMMITTED changes to TRACKED files, so it cannot fast-forward and will NOT be refreshed.' "$UPDATER"; then
  ok "(8) CC CURRENCY refusal names TRACKED files"
else
  bad "(8) CC CURRENCY refusal message missing or does not say TRACKED"
fi
if grep -qF 'has UNCOMMITTED local changes to TRACKED files — refresh SKIPPED.' "$UPDATER"; then
  ok "(8) DIRTY-CHECKOUT GUARD refusal names TRACKED files"
else
  bad "(8) DIRTY-CHECKOUT GUARD refusal message missing or does not say TRACKED"
fi
if grep -qF 'untracked file(s) in $_d — not dirt, refresh proceeds.' "$UPDATER"; then
  ok "(8) CC CURRENCY INFO line reports untracked files without blocking"
else
  bad "(8) CC CURRENCY untracked INFO line missing"
fi
if grep -qF 'untracked file(s) — not dirt, refresh proceeds.' "$UPDATER"; then
  ok "(8) DIRTY-CHECKOUT GUARD INFO line reports untracked files without blocking"
else
  bad "(8) DIRTY-CHECKOUT GUARD untracked INFO line missing"
fi

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
