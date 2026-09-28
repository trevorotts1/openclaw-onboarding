#!/usr/bin/env bash
# Self-test for scripts/check-doc-currency-guards.sh.
#
# Builds a throwaway fixture repo (version, cc-compat.json,
# DIRECT-TO-AGENT-UPDATE-MESSAGE.md, docs/interview-launch-recovery.md,
# TERMINOLOGY.md, MIGRATION.md, and a real persona directory count) in a
# temp dir, with a copy of the real script inside it (the script locates its
# own repo root via BASH_SOURCE, so the copy must sit at fixture/scripts/).
# Proves both directions: a matched fixture PASSES, and each of the five
# drift shapes the script exists to catch independently FAILS it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REAL_SCRIPT="$REPO_ROOT/scripts/check-doc-currency-guards.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/scripts" "$TMP/docs"
cp "$REAL_SCRIPT" "$TMP/scripts/check-doc-currency-guards.sh"

PERSONA_DIR="$TMP/22-book-to-persona-coaching-leadership-system/personas"

write_fixture() {
  local repo_ver="$1" pinned="$2" dta_cc="$3" ilr_onb="$4" ilr_cc="$5" \
        term_count="$6" migration_count="$7" real_persona_count="$8"

  echo "$repo_ver" > "$TMP/version"
  cat > "$TMP/cc-compat.json" <<EOF
{"onboardingVersion": "${repo_ver}", "commandCenter": {"pinnedTag": "${pinned}"}}
EOF

  cat > "$TMP/DIRECT-TO-AGENT-UPDATE-MESSAGE.md" <<EOF
There is an update available. The latest version is **${repo_ver}**.

This release pairs with Command Center ${dta_cc}. Some description here.
EOF

  cat > "$TMP/docs/interview-launch-recovery.md" <<EOF
# Fresh client interview launch

Paired releases: onboarding ${ilr_onb} / Command Center ${ilr_cc}. Skill 32 v1.0.0.
EOF

  cat > "$TMP/TERMINOLOGY.md" <<EOF
One of the ${term_count} personas in the \`coaching-personas\` library, matched per task.
EOF

  cat > "$TMP/MIGRATION.md" <<EOF
Indexing ${migration_count} personas and running occasional searches is well within free limits.
EOF

  rm -rf "$PERSONA_DIR"
  mkdir -p "$PERSONA_DIR"
  for i in $(seq 1 "$real_persona_count"); do
    mkdir -p "$PERSONA_DIR/persona-$i"
  done
}

run_check() {
  (cd "$TMP" && bash scripts/check-doc-currency-guards.sh) >"$TMP/out.log" 2>&1
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
write_fixture "v25.1.97" "v7.6.70" "v7.6.70" "v25.1.97" "v7.6.70" "99" "99" "99"
expect_pass "all markers in sync"

# 2. Stale DIRECT-TO-AGENT paired Command Center pin (the exact real-world
#    defect: frozen at v7.1.1 while cc-compat.json moved to v7.6.70) -> fails.
write_fixture "v25.1.97" "v7.6.70" "v7.1.1" "v25.1.97" "v7.6.70" "99" "99" "99"
expect_fail "stale DIRECT-TO-AGENT paired Command Center pin"

# 3. Stale interview-launch-recovery onboarding version -> fails.
write_fixture "v25.1.97" "v7.6.70" "v7.6.70" "v25.0.16" "v7.6.70" "99" "99" "99"
expect_fail "stale interview-launch-recovery onboarding version"

# 4. Stale interview-launch-recovery Command Center version -> fails.
write_fixture "v25.1.97" "v7.6.70" "v7.6.70" "v25.1.97" "v7.1.5" "99" "99" "99"
expect_fail "stale interview-launch-recovery Command Center version"

# 5. Stale TERMINOLOGY.md persona count (the exact real-world defect: 81
#    quoted against a real count of 99) -> fails.
write_fixture "v25.1.97" "v7.6.70" "v7.6.70" "v25.1.97" "v7.6.70" "81" "99" "99"
expect_fail "stale TERMINOLOGY.md persona count"

# 6. Stale MIGRATION.md persona count (the exact real-world defect: 40
#    quoted against a real count of 99) -> fails.
write_fixture "v25.1.97" "v7.6.70" "v7.6.70" "v25.1.97" "v7.6.70" "99" "40" "99"
expect_fail "stale MIGRATION.md persona count"

echo ""
echo "check-doc-currency-guards.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
