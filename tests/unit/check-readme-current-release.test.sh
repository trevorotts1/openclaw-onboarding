#!/usr/bin/env bash
# Self-test for scripts/check-readme-current-release.sh.
#
# Builds a throwaway fixture repo (version + README.md + cc-compat.json) in a
# temp dir, with a copy of the real script inside it (the script locates its
# own repo root via BASH_SOURCE, so the copy must sit at fixture/scripts/).
# Proves both directions: a matched fixture PASSES, and each of the three
# drift shapes the script exists to catch (stale heading, stale banner
# version, stale paired-CC pin) independently FAILS it — the mutation proof
# that stops this test from passing vacuously.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REAL_SCRIPT="$REPO_ROOT/scripts/check-readme-current-release.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/scripts"
cp "$REAL_SCRIPT" "$TMP/scripts/check-readme-current-release.sh"

write_fixture() {
  local repo_ver="$1" header_ver="$2" banner_ver="$3" pinned="$4" banner_cc="$5"
  echo "$repo_ver" > "$TMP/version"
  cat > "$TMP/README.md" <<EOF
# Fixture

> **${banner_ver} — Some description.** Paired Command Center: **${banner_cc}**.

## Current release: ${header_ver}

Body text.
EOF
  cat > "$TMP/cc-compat.json" <<EOF
{"onboardingVersion": "${repo_ver}", "commandCenter": {"pinnedTag": "${pinned}"}}
EOF
}

run_check() {
  (cd "$TMP" && bash scripts/check-readme-current-release.sh) >"$TMP/out.log" 2>&1
}

pass=0
fail=0

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

# 1. Everything in sync -> passes.
write_fixture "v25.1.95" "v25.1.95" "v25.1.95" "v7.6.68" "v7.6.68"
expect_pass "all markers in sync"

# 2. Stale "## Current release" heading (the exact real-world defect: heading
#    frozen at an old version while /version moved on) -> fails.
write_fixture "v25.1.95" "v25.0.10" "v25.1.95" "v7.6.68" "v7.6.68"
expect_fail "stale '## Current release' heading"

# 3. Stale top-banner version token -> fails.
write_fixture "v25.1.95" "v25.1.95" "v25.0.16" "v7.6.68" "v7.6.68"
expect_fail "stale top-banner version"

# 4. Stale "Paired Command Center" pin (the exact real-world defect: banner
#    pin frozen at v7.1.5 while cc-compat.json pinnedTag moved to v7.6.68) -> fails.
write_fixture "v25.1.95" "v25.1.95" "v25.1.95" "v7.6.68" "v7.1.5"
expect_fail "stale paired Command Center pin"

echo ""
echo "check-readme-current-release.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
