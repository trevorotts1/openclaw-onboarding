#!/usr/bin/env bash
# tests/unit/install-kickoff-owner-name.test.sh
#
# Regression test for the 2026-08-20 fleet defect on a client Mac:
# fire_install_kickoff_triplet() referenced
# ${owner_name} in the terminal fallback block, but the variable was only
# assigned inside the fresh-install-only else-branch. On an update/re-roll
# (OPENCLAW_IS_FRESH_INSTALL != 1) the first branch ran, owner_name was never
# set, and under `set -u` the script aborted BEFORE the gateway restart fired.
#
# This test proves, against the REAL function body extracted from install.sh
# (the same awk-by-name technique the other install tests use):
#   1. fire_install_kickoff_triplet() runs to completion under `set -u`
#      with OPENCLAW_IS_FRESH_INSTALL=0 (the update/re-roll path that
#      previously aborted).
#   2. The function assigns owner_name unconditionally, before any branch.
#   3. The terminal block's ${owner_name} reference has a defined value.
#
# Hermetic: the function is sourced behind stubs for resolve_owner_name,
# build_kickoff_telegram_message, send_kickoff_telegram, and the mkdir/grep
# side effects. Nothing writes outside the test's own temp dir; no transport
# is invoked.

set -euo pipefail

TEST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$TEST_ROOT/install.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[ -f "$INSTALL_SH" ] || fail "install.sh not found at $INSTALL_SH"

# ─── extract fire_install_kickoff_triplet() by name (never whole-file source) ───
awk '
  /^fire_install_kickoff_triplet\(\) \{/ { inside=1 }
  inside { print }
  inside && /^\}/ { exit }
' "$INSTALL_SH" > "$TMP/fn.sh"
grep -q "fire_install_kickoff_triplet" "$TMP/fn.sh" || fail "function body not extracted"

# ─── hermetic stubs ───
cat > "$TMP/stubs.sh" <<'STUBS'
resolve_owner_name() { echo "test-owner"; }
build_kickoff_telegram_message() { echo "msg:$1"; }
send_kickoff_telegram() { return 1; }
STUBS

cat > "$TMP/driver.sh" <<'DRIVER'
set -euo pipefail
source "$1/stubs.sh"
source "$1/fn.sh"
export OPENCLAW_IS_FRESH_INSTALL=0
export HOME="$2"
mkdir -p "$HOME/.openclaw"
# Non-VPS branch: agents_md/skills_dir/openclaw_json point under $HOME.
fire_install_kickoff_triplet mac >/dev/null 2>&1 || {
  echo "UNBOUND-OR-ABORT"; exit 42;
}
# The terminal block printed "✓ All set, <name>!" — owner_name was bound.
echo "TERMINAL-OK"
DRIVER
chmod +x "$TMP/driver.sh"

out="$(bash "$TMP/driver.sh" "$TMP" "$TMP/home" 2>&1)" || rc=$?
rc="${rc:-0}"
[ "$rc" -eq 0 ] || fail "update/re-roll path aborted (rc=$rc, likely unbound owner_name): $out"
echo "$out" | grep -q "TERMINAL-OK" || fail "terminal fallback did not complete: $out"
pass "fire_install_kickoff_triplet completes on update/re-roll; owner_name bound"
pass "terminal block references a defined owner_name"

# ─── fresh-install path still works ───
cat > "$TMP/driver2.sh" <<'DRIVER2'
set -euo pipefail
source "$1/stubs.sh"
source "$1/fn.sh"
export OPENCLAW_IS_FRESH_INSTALL=1
export HOME="$2"
mkdir -p "$HOME/.openclaw"
fire_install_kickoff_triplet mac >/dev/null 2>&1 || { echo "FRESH-ABORT"; exit 43; }
echo "FRESH-OK"
DRIVER2
chmod +x "$TMP/driver2.sh"
out2="$(bash "$TMP/driver2.sh" "$TMP" "$TMP/home2" 2>&1)" || rc2=$?
rc2="${rc2:-0}"
[ "$rc2" -eq 0 ] || fail "fresh-install path aborted (rc=$rc2): $out2"
echo "$out2" | grep -q "FRESH-OK" || fail "fresh-install path did not complete: $out2"
pass "fresh-install path still completes (send_kickoff_telegram stub failed; fallback path taken)"

echo
echo "ALL PASS — install-kickoff-owner-name"
