#!/usr/bin/env bash
# Self-test for scripts/check-tag-on-main.sh (tag-on-main-guard workflow).
#
# Builds a throwaway git repo with real commits, branches and annotated tags
# (the script walks `git rev-parse` / `git merge-base --is-ancestor`, so a
# file-only fixture cannot exercise it). Proves the three cases the guard
# exists to tell apart: a tag whose commit IS on main passes; a tag whose
# commit sits only on a side branch (the exact 2026-09-29 v25.2.16-on-
# 3aa92592 landmine shape) fails; and a tag that was never created at all
# also fails, rather than silently passing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REAL_SCRIPT="$REPO_ROOT/scripts/check-tag-on-main.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git -C "$TMP" init -q -b main
git -C "$TMP" config user.email "test@example.com"
git -C "$TMP" config user.name "Test"

commit() {
  git -C "$TMP" commit --allow-empty -q -m "$1"
}

pass=0
fail=0

run_check() {
  local tag="$1"
  # The script resolves refs via `git` in its cwd and takes an explicit
  # --main-ref (mirrors check-tag-ancestry.py's --main-ref), so run it FROM
  # the fixture repo against the fixture's own main branch.
  (cd "$TMP" && bash "$REAL_SCRIPT" "$tag" --main-ref main) >"$TMP/out.log" 2>&1
}

expect_pass() {
  local name="$1" tag="$2"
  if run_check "$tag"; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL (expected pass): $name"
    cat "$TMP/out.log"
    fail=$((fail + 1))
  fi
}

expect_fail() {
  local name="$1" tag="$2"
  if run_check "$tag"; then
    echo "FAIL (expected failure, but check passed): $name"
    cat "$TMP/out.log"
    fail=$((fail + 1))
  else
    echo "PASS: $name correctly rejected"
    pass=$((pass + 1))
  fi
}

# 1. Tag's commit IS on main -> passes.
commit "first commit on main"
git -C "$TMP" tag -a v1.0.0 -m "v1.0.0"
expect_pass "tag on main passes" "v1.0.0"

# 2. Tag's commit sits only on a side branch, never merged to main -> fails.
#    This is the exact landmine shape: v25.2.16 pushed onto an unmerged
#    draft-PR commit instead of a commit that reached main.
git -C "$TMP" checkout -q -b side-branch
commit "unmerged draft-PR commit"
git -C "$TMP" tag -a v2.0.0 -m "v2.0.0"
git -C "$TMP" checkout -q main
expect_fail "tag on unmerged side branch fails" "v2.0.0"

# 3. Tag was never created at all -> fails (never silently passes on a
#    ref that doesn't resolve).
expect_fail "missing tag fails" "v9.9.9"

echo ""
echo "check-tag-on-main.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
