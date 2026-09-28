#!/usr/bin/env bash
# Self-test for scripts/check-changelog-full-history.py (guard G2-EXT).
#
# Builds a throwaway git repo with real annotated tags (the script walks
# `git for-each-ref refs/tags`, so a file-only fixture cannot exercise it —
# unlike check-readme-current-release.sh's fixture, this one needs actual
# git history). Proves: a fully-covered tag set passes; a gap not in the
# ledger fails (new regression, at ANY version, not just below v11 — proves
# the "no floor" claim); a stale ledger entry whose tag now HAS a CHANGELOG
# header fails (the ledger-can-only-shrink direction); and a lightweight tag
# is correctly ignored, exactly like G2/G4.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REAL_SCRIPT="$REPO_ROOT/scripts/check-changelog-full-history.py"

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
  # The script resolves tags via `git` in its cwd (no --repo option, same as
  # check-tag-ancestry.py / check-released-versions-tagged.py), so it must run
  # FROM the fixture repo; --changelog/--ledger are then plain relative names.
  (cd "$TMP" && python3 "$REAL_SCRIPT" --changelog CHANGELOG.md --ledger ledger.txt) >"$TMP/out.log" 2>&1
}

expect_pass() {
  local name="$1"
  if run_check; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL (expected pass): $name"
    cat "$TMP/out.log"
    fail=$((fail + 1))
  fi
}

expect_fail() {
  local name="$1"
  if run_check; then
    echo "FAIL (expected failure, but check passed): $name"
    cat "$TMP/out.log"
    fail=$((fail + 1))
  else
    echo "PASS: $name correctly rejected"
    pass=$((pass + 1))
  fi
}

# Seed two releases: v1.0.0 (pre-v11-style, will be grandfathered) and
# v25.1.0 (v11+-style, must be covered directly).
commit "v1.0.0"
git -C "$TMP" tag -a v1.0.0 -m "v1.0.0"
commit "v25.1.0"
git -C "$TMP" tag -a v25.1.0 -m "v25.1.0"
# A lightweight tag must be ignored entirely, same as G2/G4.
git -C "$TMP" tag v9.9.9

# 1. Both tags covered by CHANGELOG.md, empty ledger -> passes.
cat > "$TMP/CHANGELOG.md" <<'EOF'
## [v25.1.0]  -  2026-01-01  -  Something shipped.

## [v1.0.0]  -  2025-01-01  -  Initial release.
EOF
: > "$TMP/ledger.txt"
expect_pass "both tags covered, empty ledger"

# 2. v1.0.0's entry removed and NOT grandfathered -> fails (new gap, proves
#    there is no v11 floor — even a pre-v11-shaped tag must be covered or
#    ledgered).
cat > "$TMP/CHANGELOG.md" <<'EOF'
## [v25.1.0]  -  2026-01-01  -  Something shipped.
EOF
: > "$TMP/ledger.txt"
expect_fail "gap not in ledger fails, even below v11 (no floor)"

# 3. Same gap, now grandfathered in the ledger -> passes.
cat > "$TMP/CHANGELOG.md" <<'EOF'
## [v25.1.0]  -  2026-01-01  -  Something shipped.
EOF
echo "v1.0.0  # pre-v11 backlog, test fixture" > "$TMP/ledger.txt"
expect_pass "ledgered gap passes"

# 4. v25.1.0 (the v11+-style tag) loses its entry and is NOT ledgered -> fails.
cat > "$TMP/CHANGELOG.md" <<'EOF'
## [v1.0.0]  -  2025-01-01  -  Initial release.
EOF
: > "$TMP/ledger.txt"
expect_fail "v11+-style tag missing entry fails"

# 5. Stale ledger entry: v1.0.0 is grandfathered but ALSO now has a real
#    CHANGELOG entry -> fails (the ledger-can-only-shrink direction, exactly
#    like known-orphan-tags.txt / known-untagged-releases.txt).
cat > "$TMP/CHANGELOG.md" <<'EOF'
## [v25.1.0]  -  2026-01-01  -  Something shipped.

## [v1.0.0]  -  2025-01-01  -  Initial release.
EOF
echo "v1.0.0  # pre-v11 backlog, test fixture" > "$TMP/ledger.txt"
expect_fail "stale ledger entry (already repaid) fails"

echo ""
echo "check-changelog-full-history.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
