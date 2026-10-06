#!/usr/bin/env bash
# tests/unit/two-roots-guard-canonical-paths.test.sh
# -----------------------------------------------------------------------------
# Regression lock for the two-roots guard in platform/common.sh.
#
# THE BUG THIS LOCKS. oc_set_platform_paths refused to run when it saw both
# /data/.openclaw and $HOME/.openclaw, and it decided that by comparing PATH
# STRINGS. On a container image whose /data is a symlink to the node user's
# home, those two names are ONE directory on ONE inode. The guard fired anyway
# and aborted the updater with
#     Two OpenClaw roots exist; set OPENCLAW_ROOT to the intended client installation.
# The operator had to pass OPENCLAW_ROOT by hand on every run. A symlink is not
# a second installation.
#
# WHAT THIS TEST PROVES.
#   T1  oc_canonical_path collapses a symlinked spelling to the real directory
#   T2  oc_canonical_path keeps two genuinely separate directories separate
#       (the canonicalizer is not a rubber stamp that equates everything)
#   T3  the guard is NOT vacuous: two REAL roots still abort, rc 1, with the
#       documented message and both resolved paths named
#   T4  one root reached by two names PASSES and selects $HOME/.openclaw
#   T5  the sandbox rewrite that makes T3/T4 possible actually rewrote the
#       source (a silent no-op substitution would make both cases test nothing)
#   T6  the shipped guard calls the canonicalizer instead of comparing strings
#
# Hermetic: mktemp -d sandbox, a stubbed `uname` so the Linux/vps branch is
# reachable from any runner, and a sandbox COPY of common.sh whose hardcoded
# /data paths are repointed inside the sandbox (/data cannot be created on a
# CI runner). No ~/.openclaw, no network, no fleet box, no writes to the repo.
# Bash 3.2 safe: no associative arrays, no mapfile, no case modifiers.
# Exit 0 = all pass.
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMMON="$REPO_ROOT/platform/common.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }

echo "=== two-roots-guard-canonical-paths.test.sh ==="

if [ ! -f "$COMMON" ]; then
  bad "platform/common.sh missing at $COMMON"
  printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
  exit 1
fi

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/two-roots-guard.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# A stubbed uname keeps the vps branch reachable on a macOS runner. Nothing
# else about the host is faked.
mkdir -p "$SANDBOX/bin"
cat > "$SANDBOX/bin/uname" <<'STUB'
#!/bin/bash
printf '%s\n' Linux
STUB
chmod +x "$SANDBOX/bin/uname"

# ---------------------------------------------------------------------------
# T1/T2 exercise the REAL shipped function, sourced as-is. No rewriting.
# ---------------------------------------------------------------------------
# shellcheck source=/dev/null
source "$COMMON"

if ! declare -F oc_canonical_path >/dev/null 2>&1; then
  bad "oc_canonical_path is not defined after sourcing platform/common.sh"
  printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
  exit 1
fi
ok "oc_canonical_path is defined after sourcing platform/common.sh"

T1="$SANDBOX/t1"
mkdir -p "$T1/real/.openclaw"
ln -s "$T1/real" "$T1/alias"
real_canonical="$(oc_canonical_path "$T1/real/.openclaw")"
alias_canonical="$(oc_canonical_path "$T1/alias/.openclaw")"
if [ -n "$real_canonical" ] && [ "$real_canonical" = "$alias_canonical" ]; then
  ok "symlinked spelling collapses to the real directory ($alias_canonical)"
else
  bad "symlink not collapsed: real='$real_canonical' alias='$alias_canonical'"
fi

T2="$SANDBOX/t2"
mkdir -p "$T2/one/.openclaw" "$T2/two/.openclaw"
one_canonical="$(oc_canonical_path "$T2/one/.openclaw")"
two_canonical="$(oc_canonical_path "$T2/two/.openclaw")"
if [ -n "$one_canonical" ] && [ "$one_canonical" != "$two_canonical" ]; then
  ok "two separate directories stay separate ($one_canonical vs $two_canonical)"
else
  bad "canonicalizer equated two real directories: '$one_canonical' '$two_canonical'"
fi

# ---------------------------------------------------------------------------
# The sandbox copy. /data is not creatable on a CI runner, so the two hardcoded
# /data paths are repointed into the sandbox. Every other line is byte-identical
# to the shipped file, so the branch under test is the shipped branch.
# ---------------------------------------------------------------------------
FAKE_DATA="$SANDBOX/fakeroot/data"
SANDBOX_COMMON="$SANDBOX/common.sh"
sed -e "s#-d /data/\.openclaw#-d $FAKE_DATA/.openclaw#g" \
    -e "s#root=/data/\.openclaw#root=$FAKE_DATA/.openclaw#g" \
    -e "s#oc_canonical_path /data/\.openclaw#oc_canonical_path $FAKE_DATA/.openclaw#g" \
    -e "s#\"\$HOME/\.openclaw\" != /data/\.openclaw#\"\$HOME/.openclaw\" != $FAKE_DATA/.openclaw#g" \
    -e "s#-d /data &&#-d $FAKE_DATA \&\&#g" \
    "$COMMON" > "$SANDBOX_COMMON"

# T5 first: if the rewrite silently matched nothing, T3 and T4 would both be
# testing a branch that can never be entered. Every one of the five rewrite
# rules must have landed. T3 then proves it behaviorally: the runner has no real
# /data/.openclaw, so an abort there is only possible if the branch was
# genuinely reachable through the sandbox paths.
if ! cmp -s "$COMMON" "$SANDBOX_COMMON" \
   && grep -qF -- "-d $FAKE_DATA/.openclaw" "$SANDBOX_COMMON" \
   && grep -qF -- "root=$FAKE_DATA/.openclaw" "$SANDBOX_COMMON" \
   && grep -qF -- "!= $FAKE_DATA/.openclaw" "$SANDBOX_COMMON" \
   && grep -qF -- "oc_canonical_path $FAKE_DATA/.openclaw" "$SANDBOX_COMMON" \
   && grep -qF -- "-d $FAKE_DATA &&" "$SANDBOX_COMMON"; then
  ok "sandbox rewrite repointed every hardcoded /data path (guard is reachable)"
else
  bad "sandbox rewrite incomplete; T3/T4 would prove nothing"
fi

run_guard() {
  # $1 = HOME for the run. Prints OC_CONFIG on success; stderr is kept.
  PATH="$SANDBOX/bin:$PATH" HOME="$1" \
    env -u OPENCLAW_ROOT -u OC_ROOT -u OC_CONFIG -u OPENCLAW_PLATFORM \
        -u OPENCLAW_WORKSPACE_PATH -u OPENCLAW_WORKSPACE_ROOT \
    /bin/bash -c 'source "$1" && oc_set_platform_paths && printf "ROOT:%s\n" "$OC_CONFIG"' \
      _ "$SANDBOX_COMMON" 2>"$SANDBOX/stderr.txt"
}

# ---------------------------------------------------------------------------
# T3 two GENUINELY distinct roots must still abort.
# ---------------------------------------------------------------------------
rm -rf "$SANDBOX/fakeroot"
HOME_REAL="$SANDBOX/home-distinct"
mkdir -p "$HOME_REAL/.openclaw" "$FAKE_DATA/.openclaw"
out="$(run_guard "$HOME_REAL")"
rc=$?
err="$(cat "$SANDBOX/stderr.txt")"
if [ "$rc" -ne 0 ] \
   && printf '%s' "$err" | grep -q 'Two OpenClaw roots exist' \
   && printf '%s' "$err" | grep -q "$HOME_REAL/.openclaw resolves to" \
   && [ -z "$out" ]; then
  ok "two distinct roots still abort (rc $rc) and both resolved paths are named"
else
  bad "two distinct roots did not abort as documented: rc=$rc out='$out' err='$err'"
fi

# ---------------------------------------------------------------------------
# T4 one root reached by two names must PASS and pick $HOME/.openclaw.
# ---------------------------------------------------------------------------
rm -rf "$SANDBOX/fakeroot"
HOME_LINKED="$SANDBOX/home-linked"
mkdir -p "$HOME_LINKED/.openclaw" "$SANDBOX/fakeroot"
ln -s "$HOME_LINKED" "$FAKE_DATA"
out="$(run_guard "$HOME_LINKED")"
rc=$?
err="$(cat "$SANDBOX/stderr.txt")"
if [ "$rc" -eq 0 ] && [ "$out" = "ROOT:$HOME_LINKED/.openclaw" ]; then
  ok "symlinked /data collapses to one root and selects \$HOME/.openclaw"
else
  bad "symlinked /data still refused or picked the wrong root: rc=$rc out='$out' err='$err'"
fi
if printf '%s' "$err" | grep -q 'One OpenClaw root reached by two paths'; then
  ok "the collapse is logged with both candidate paths"
else
  bad "the collapse was not logged: err='$err'"
fi

# ---------------------------------------------------------------------------
# T6 source-level: the guard must canonicalize, not string-compare.
# ---------------------------------------------------------------------------
if grep -q 'oc_canonical_path "\$HOME/\.openclaw"' "$COMMON" \
   && grep -q 'oc_canonical_path /data/\.openclaw' "$COMMON"; then
  ok "the shipped guard canonicalizes both candidates before comparing"
else
  bad "the shipped guard no longer canonicalizes both candidates"
fi

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
