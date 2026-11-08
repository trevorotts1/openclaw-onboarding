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
#                 $4=HOME (default: a sandbox with no library, so the run is
#                    hermetic — the stanza now also searches $HOME and the
#                    test machine's own $HOME/.openclaw must never leak in)
HOME_NONE="$WORK/home-none"
mkdir -p "$HOME_NONE"
resolve_lib() {
    (
        cd "$3" || exit 1
        HOME="${4:-$HOME_NONE}"
        export HOME
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

# =============================================================================
# G/H/I: THE CANONICAL PATH — `curl ... | bash`
# =============================================================================
# Under `curl ... | bash` the entry script has no path: BASH_SOURCE[0] is empty,
# `dirname ''` is '.', so _SCRIPT_DIR becomes the CALLER'S CWD, and
# platform/mac/bootstrap.sh is curl-fetched into a mktemp file. Both of the
# stanza's location-derived candidates (1-3) therefore miss on any box whose
# library is not in the cwd — which is every box. Candidates anchored to $HOME
# are what close this.
#
# Faithful setup: the REAL bootstrap.sh is copied ALONE into a temp dir (no
# checkout around it, exactly like the mktemp fetch), the stanza is extracted
# from that copy, and the copy's own location root resolves to the temp dir.
# HOME is a fake box, the cwd is a foreign dir that is not HOME, and
# OPENCLAW_ROOT is unset (nothing called oc_set_platform_paths).
TMPFETCH="$WORK/tmpfetch"
mkdir -p "$TMPFETCH"
cp "$BOOTSTRAP" "$TMPFETCH/bootstrap.sh"
SNIP_COPY="$(awk '/^_PR_LIB=/ { c=1 } c && /^if / { exit } c { print }' "$TMPFETCH/bootstrap.sh")"
[ -n "$SNIP_COPY" ] || { echo "  FAIL: could not extract the stanza from the temp copy"; exit 1; }
{
    printf '%s\n' "$SNIP_COPY"
    printf 'printf "%%s\\n" "${_PR_LIB:-}"\n'
} > "$TMPFETCH/resolve.sh"

FOREIGN="$WORK/foreign-cwd"
mkdir -p "$FOREIGN"
[ "$FOREIGN" != "$HOME" ] || { echo "  FAIL: fixture broken — foreign cwd is HOME"; exit 1; }

# piped_resolve <fake HOME> -> the path the fetched bootstrap would pick
piped_resolve() {
    (
        cd "$FOREIGN" || exit 1
        HOME="$1"
        export HOME
        unset OPENCLAW_ROOT _SCRIPT_DIR
        _SCRIPT_DIR="$FOREIGN"
        export _SCRIPT_DIR
        bash "$TMPFETCH/resolve.sh"
    ) 2>/dev/null
}

# ---- G: piped fetch, library ONLY at $HOME/.openclaw (layout 1) -----------
# This is the case that separates old from new: before the $HOME anchors it
# resolves to nothing and the gate is skipped with rc 0.
PIPED_BOX="$WORK/piped-box"
mkdir -p "$PIPED_BOX/.openclaw/platform/mac/power-resilience"
echo '# placeholder — resolution only' > "$PIPED_BOX/.openclaw/$LIB_REL"
PIPED_LIB="$PIPED_BOX/.openclaw/$LIB_REL"
[ ! -e "$PIPED_BOX/platform" ] || { echo "  FAIL: fixture broken — \$HOME/platform must not exist"; exit 1; }
G_OUT="$(piped_resolve "$PIPED_BOX")"
if [ "$G_OUT" = "$PIPED_LIB" ]; then
    pass "G: piped fetch from a foreign cwd finds the library at \$HOME/.openclaw (install root)"
else
    fail "G: piped fetch from a foreign cwd resolved '${G_OUT:-<empty>}' — expected $PIPED_LIB"
fi

# ---- H: piped fetch, library ONLY at $HOME/.openclaw/onboarding -----------
# The second real layout measured on a live Mac. None of candidates 1-4 reach
# it, so it must be anchored explicitly.
PIPED_BOX2="$WORK/piped-box2"
mkdir -p "$PIPED_BOX2/.openclaw/onboarding/platform/mac/power-resilience"
echo '# placeholder — resolution only' > "$PIPED_BOX2/.openclaw/onboarding/$LIB_REL"
PIPED_LIB2="$PIPED_BOX2/.openclaw/onboarding/$LIB_REL"
H_OUT="$(piped_resolve "$PIPED_BOX2")"
if [ "$H_OUT" = "$PIPED_LIB2" ]; then
    pass "H: piped fetch finds the library in the \$HOME/.openclaw/onboarding mirror"
else
    fail "H: piped fetch resolved '${H_OUT:-<empty>}' — expected $PIPED_LIB2"
fi

# ---- I: piped fetch, NO library anywhere -> warns, never silently passes ---
# Run the REAL gate block (stanza + the if/else that consumes it) from the temp
# copy, on a box with no library in any candidate root. The gate may not run,
# so the ONLY acceptable outcome is the explicit WARNING on stderr that names
# what it searched. A silent rc 0 is the defect.
GATE_TAIL="$(awk '/^_PR_LIB=/ { c=1 } c { print }' "$TMPFETCH/bootstrap.sh")"
{
    printf '%s\n' "$GATE_TAIL"
} > "$TMPFETCH/gate.sh"
NOLIB_HOME="$WORK/nolib-home"
mkdir -p "$NOLIB_HOME"
I_ERR="$(
    cd "$FOREIGN" || exit 1
    HOME="$NOLIB_HOME"
    export HOME
    unset OPENCLAW_ROOT _SCRIPT_DIR
    _SCRIPT_DIR="$FOREIGN"
    export _SCRIPT_DIR
    bash "$TMPFETCH/gate.sh" 2>&1 >/dev/null
)"
if printf '%s' "$I_ERR" | grep -q 'WARNING: power-resilience library not found'; then
    pass "I: a piped fetch with no library anywhere warns loudly (never a silent pass)"
else
    fail "I: no library anywhere produced no WARNING — the gate skipped silently"
fi
if printf '%s' "$I_ERR" | grep -q '/platform/mac/power-resilience/lib-power-resilience.sh'; then
    pass "I: the warning names the paths it searched"
else
    fail "I: the warning did not name any searched path"
fi
if printf '%s' "$I_ERR" | grep -q "$NOLIB_HOME/.openclaw/platform/mac/power-resilience"; then
    pass "I: the searched list includes the \$HOME install-root anchor"
else
    fail "I: the searched list does not include the \$HOME install-root anchor"
fi

# ---- J: the \$HOME anchors are present in the shipped stanza --------------
for _anchor in '${HOME:+$HOME/.openclaw}' '${HOME:+$HOME/.openclaw/onboarding}'; do
    if printf '%s' "$SNIP_BODY" | grep -qF "$_anchor"; then
        pass "J: stanza carries the install-root anchor $_anchor"
    else
        fail "J: stanza is missing the install-root anchor $_anchor"
    fi
done

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
