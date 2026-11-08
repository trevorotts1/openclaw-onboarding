#!/usr/bin/env bash
# =============================================================================
# tests/unit/power-resilience-lib-path.test.sh
# =============================================================================
# Regression test for the SILENT-SKIP defect (measured on rescue-lyric-hawkins).
#
# The defect: platform/mac/bootstrap.sh built _PR_LIB from ONE relative path
# rooted at ${_SCRIPT_DIR:-...}. _SCRIPT_DIR is the directory of the ENTRY
# script (install.sh / update-skills.sh), not the checkout, and its `|| pwd`
# fallback silently substitutes the CALLER'S CURRENT DIRECTORY whenever the
# entry script is piped, temp-file bootstrapped, or run by bare name.
#
# Measured on the box: the updater was entered from the login cwd ($HOME), so
# _PR_LIB became
#   $HOME/platform/mac/power-resilience/lib-power-resilience.sh
# the `.openclaw` segment was DROPPED, while the library actually sat at
#   $HOME/.openclaw/platform/mac/power-resilience/lib-power-resilience.sh
# The `[ -f "$_PR_LIB" ]` test therefore failed, the else-branch only echoed a
# WARNING, and the ENTIRE outage-survival gate (pr_preflight_gate,
# pr_apply_pmset, pr_check_ethernet) was skipped with rc 0. pmset autorestart
# was never set, so that box would stay OFF when mains returned.
#
# WHY THE EXISTING SUITE COULD NOT CATCH THIS: power-resilience-gate.test.sh
# derives LIB from REPO_ROOT, so it always finds the library and never
# exercises _PR_LIB resolution from a foreign cwd. Its bootstrap checks are
# wiring greps (the call sites exist), not reachability.
#
# WHAT THIS TEST DOES: it extracts the ACTUAL resolution stanza OUT of the
# shipped platform/mac/bootstrap.sh at runtime — no copy, so a change to the
# real code is picked up here automatically — runs it as its own script from a
# foreign cwd, and asserts which path wins.
#
# It FAILS on the old single-path code and PASSES on the searching code. Every
# case below names which of the two it separates.
#
# Fully offline. No root. No live box. macOS bash 3.2 safe (no arrays).
# Exit 0 = all pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$REPO_ROOT/platform/mac/bootstrap.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== power-resilience-lib-path.test.sh ==="

[ -f "$BOOTSTRAP" ] || { echo "  FAIL: bootstrap not found at $BOOTSTRAP"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---- Extract the real resolution stanza from the shipped bootstrap ----------
# From the first `_PR_LIB=` assignment up to (not including) the first line
# that starts with `if ` — i.e. exactly the code that decides _PR_LIB.
SNIP_BODY="$(awk '/^_PR_LIB=/ { c=1 } c && /^if / { exit } c { print }' "$BOOTSTRAP")"

if [ -z "$SNIP_BODY" ]; then
    echo "  FAIL: could not extract the _PR_LIB resolution stanza from bootstrap.sh"
    exit 1
fi

# Make it a standalone script whose BASH_SOURCE is inside $WORK (so the
# bootstrap.sh-derived candidate resolves to a temp dir with nothing in it —
# faithful to the temp-file bootstrap that Lyric's updater actually used).
mkdir -p "$WORK/snip/scripts"
{
    printf '%s\n' "$SNIP_BODY"
    printf 'printf "%%s\\n" "${_PR_LIB:-}"\n'
} > "$WORK/snip/scripts/resolve.sh"

# ---- Fake client box that reproduces Lyric's measured layout ----------------
# $BOX plays $HOME. The library exists ONLY under $BOX/.openclaw.
# $BOX/platform does NOT exist — exactly the measured box.
BOX="$WORK/box"
LIB_REL="platform/mac/power-resilience/lib-power-resilience.sh"
mkdir -p "$BOX/.openclaw/platform/mac/power-resilience"
echo '# placeholder — resolution only, never sourced by this test' \
    > "$BOX/.openclaw/$LIB_REL"
BOX_LIB="$BOX/.openclaw/$LIB_REL"

[ -f "$BOX_LIB" ] || { echo "  FAIL: fixture broken — $BOX_LIB missing"; exit 1; }
[ ! -e "$BOX/platform" ] || { echo "  FAIL: fixture broken — $BOX/platform must not exist"; exit 1; }

# run the stanza: $1=_SCRIPT_DIR  $2=OPENCLAW_ROOT (may be empty)  $3=cwd
resolve_lib() {
    (
        cd "$3" || exit 1
        unset OPENCLAW_ROOT
        unset _SCRIPT_DIR
        [ -z "$1" ] || _SCRIPT_DIR="$1"
        [ -z "$1" ] || export _SCRIPT_DIR
        [ -z "$2" ] || OPENCLAW_ROOT="$2"
        [ -z "$2" ] || export OPENCLAW_ROOT
        bash "$WORK/snip/scripts/resolve.sh"
    ) 2>/dev/null
}

# ---- A: THE DEFECT — entry run from $HOME, .openclaw segment dropped --------
# _SCRIPT_DIR=$BOX (= the `|| pwd` result), cwd=$BOX, library only under
# $BOX/.openclaw. Old code resolves "$BOX/platform/..." (missing) -> skipped
# gate. New code finds candidate 2. This is the case that separates old/new.
A_OUT="$(resolve_lib "$BOX" "" "$BOX")"
if [ "$A_OUT" = "$BOX_LIB" ]; then
    pass "A: library resolves to the .openclaw layout when the entry runs from \$HOME"
else
    fail "A: expected $BOX_LIB, got '${A_OUT:-<empty>}' — the .openclaw segment is still dropped"
fi

# ---- B: unchanged behaviour when the entry already resolves ----------------
# _SCRIPT_DIR=$REPO_ROOT with the library in-tree -> first candidate wins.
# Must pass on BOTH old and new: this proves the fix did not change the
# behaviour that already worked.
B_OUT="$(resolve_lib "$REPO_ROOT" "" "$REPO_ROOT")"
if [ "$B_OUT" = "$REPO_ROOT/$LIB_REL" ]; then
    pass "B: the pre-existing in-checkout resolution is unchanged"
else
    fail "B: expected $REPO_ROOT/$LIB_REL, got '${B_OUT:-<empty>}'"
fi

# ---- C: a genuine miss must stay a miss (never a silent pass) --------------
# No library anywhere. Assert the resolved path is not an existing file, so
# the if-branch cannot run, so the WARNING branch is the only path. This locks
# in that the search cannot invent a hit.
BOX2="$WORK/box2"
mkdir -p "$BOX2"
C_OUT="$(resolve_lib "$BOX2" "" "$BOX2")"
if [ ! -f "${C_OUT:-/nonexistent}" ]; then
    pass "C: with no library anywhere the resolved path is not a file (gate warns)"
else
    fail "C: resolution invented an existing file at '$C_OUT' — a missing library could pass"
fi

# ---- D: OPENCLAW_ROOT is honoured (explicit override) ----------------------
ALT="$WORK/alt"
mkdir -p "$ALT/platform/mac/power-resilience"
echo '# placeholder' > "$ALT/$LIB_REL"
D_OUT="$(resolve_lib "$BOX2" "$ALT" "$BOX2")"
if [ "$D_OUT" = "$ALT/$LIB_REL" ]; then
    pass "D: \$OPENCLAW_ROOT is searched and wins when the entry dir has no library"
else
    fail "D: expected $ALT/$LIB_REL, got '${D_OUT:-<empty>}'"
fi

# ---- E: an empty candidate must be skipped, never "/platform/..." ----------
# The old fallback had no guard: a failed `cd` yielded EMPTY and produced a
# path beginning at "/platform/...". Assert the stanza refuses empty roots.
if printf '%s' "$SNIP_BODY" | grep -q '\[ -n "\$_pr_root" \]'; then
    pass "E: empty candidate roots are skipped (no /platform/... from a failed cd)"
else
    fail "E: the stanza does not guard against an empty candidate root"
fi

# ---- F: the bootstrap still refuses to fail silently ----------------------
# The warning must survive the rewrite — a missing library may never become a
# quiet pass. (Requirement: never weaken the gate.)
if grep -q 'WARNING: power-resilience library not found' "$BOOTSTRAP"; then
    pass "F: the missing-library WARNING is still emitted"
else
    fail "F: the missing-library WARNING was removed — a miss would now be silent"
fi
if grep -q 'pr_preflight_gate' "$BOOTSTRAP" && grep -q 'pr_apply_pmset' "$BOOTSTRAP"; then
    pass "F: the gate and pmset call sites are still present"
else
    fail "F: the gate or pmset call site is missing from bootstrap.sh"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
