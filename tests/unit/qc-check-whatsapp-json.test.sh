#!/usr/bin/env bash
# tests/unit/qc-check-whatsapp-json.test.sh
#
# Direct, non-hollow regression coverage for scripts/qc-check-whatsapp-json.py.
#
# THE GAP THIS CLOSES: the only prior test touching this area,
# tests/unit/whatsapp-ban.test.sh, never invokes this script at all — it
# greps OTHER files (apply-fleet-standards.sh, install.sh, FLEET-STANDARDS.md,
# KNOWN-ISSUES.md, a repo-wide "whatsapp" scan). Proof that suite is hollow
# with respect to this script: swapping scripts/qc-check-whatsapp-json.py for
# its old fail-open version (catches all parse exceptions, treats malformed
# JSON as "not applicable" -> exit 0), or reintroducing the exact one-line
# regression on the script's fail-closed branch (`return MALFORMED` ->
# `return False`), leaves that suite's "8 passed, 0 failed" output
# byte-for-byte unchanged. This file calls the script itself, as a real
# subprocess, on real fixture files, and asserts on its actual exit code —
# so a regression on ANY of the three contracted exit codes (0/1/2) turns a
# case in this file red.
#
# Contract under test (see the script's own docstring):
#   exit 0 — zero-byte file (not applicable), OR valid JSON that is not a
#            plugins.entries.whatsapp.enabled:true violation
#   exit 1 — REAL violation: valid JSON dict with
#            plugins.entries.whatsapp.enabled truthy
#   exit 2 — FAIL CLOSED: a non-empty file that could not be parsed
#            (malformed JSON, non-UTF8 bytes, unreadable path)
#
# Run:
#   bash tests/unit/qc-check-whatsapp-json.test.sh

set -euo pipefail

PASS=0
FAIL=0
ERRORS=()

ok() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/qc-check-whatsapp-json.py"

TMPDIR_T="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_T"; }
trap cleanup EXIT

# Runs the script under test directly against a fixture file and asserts
# on its actual process exit code — never on grep, never on the script's
# own stdout/stderr text.
assert_exit_code() {
  local label="$1" fixture="$2" expected="$3"
  local actual=0
  python3 "$SCRIPT" "$fixture" >/dev/null 2>&1 || actual=$?
  if [ "$actual" -eq "$expected" ]; then
    ok "$label (exit $expected)"
  else
    fail "$label — expected exit $expected, got exit $actual"
  fi
}

echo ""
echo "=== qc-check-whatsapp-json.py direct exit-code contract ==="
echo ""

if [ ! -f "$SCRIPT" ]; then
  fail "scripts/qc-check-whatsapp-json.py not found at $SCRIPT"
  echo ""
  echo "=== Results: $PASS passed, $FAIL failed ==="
  exit 1
fi

# ─── exit 0: zero-byte file (not applicable) ─────────────────────────────────
ZERO_BYTE="$TMPDIR_T/zero-byte.json"
: > "$ZERO_BYTE"
assert_exit_code "zero-byte file is not applicable" "$ZERO_BYTE" 0

# ─── exit 1: real violation, whatsapp.enabled true ───────────────────────────
ENABLED_TRUE="$TMPDIR_T/enabled-true.json"
cat > "$ENABLED_TRUE" <<'EOF'
{
  "plugins": {
    "entries": {
      "whatsapp": {
        "enabled": true
      }
    }
  }
}
EOF
assert_exit_code "whatsapp.enabled:true is a real violation" "$ENABLED_TRUE" 1

# ─── exit 2: malformed/unreadable non-empty JSON — THE UNTESTED CASE ────────
# This is the case whatsapp-ban.test.sh's mutation-proof showed was never
# exercised: an old fail-open script (or the exact `return MALFORMED` ->
# `return False` one-line regression) silently exits 0 here instead of 2.
MALFORMED="$TMPDIR_T/malformed.json"
printf '{"plugins": {"entries": {"whatsapp": {"enabled": true' > "$MALFORMED"
assert_exit_code "truncated/malformed non-empty JSON fails closed" "$MALFORMED" 2

# ─── exit 2: non-UTF8 malformed bytes ────────────────────────────────────────
NON_UTF8="$TMPDIR_T/non-utf8.json"
printf '\xff\xfe\x00\x01not valid utf-8 or json' > "$NON_UTF8"
assert_exit_code "non-UTF8 byte content fails closed" "$NON_UTF8" 2

# ─── exit 0: valid JSON, whatsapp.enabled explicitly false ──────────────────
ENABLED_FALSE="$TMPDIR_T/enabled-false.json"
cat > "$ENABLED_FALSE" <<'EOF'
{
  "plugins": {
    "entries": {
      "whatsapp": {
        "enabled": false
      }
    }
  }
}
EOF
assert_exit_code "whatsapp.enabled:false is not a violation" "$ENABLED_FALSE" 0

# ─── exit 0: valid JSON with no whatsapp key at all ──────────────────────────
NO_WHATSAPP="$TMPDIR_T/no-whatsapp.json"
cat > "$NO_WHATSAPP" <<'EOF'
{
  "plugins": {
    "entries": {
      "other-plugin": {
        "enabled": true
      }
    }
  }
}
EOF
assert_exit_code "valid JSON with no whatsapp key is not a violation" "$NO_WHATSAPP" 0

# ─── exit 0: valid JSON that is not a dict at the top level ─────────────────
NOT_A_DICT="$TMPDIR_T/not-a-dict.json"
printf '[1, 2, 3]' > "$NOT_A_DICT"
assert_exit_code "top-level JSON array is not a violation" "$NOT_A_DICT" 0

# ─── exit 2: unreadable path (OSError, not a parse error) ───────────────────
UNREADABLE="$TMPDIR_T/does-not-exist.json"
assert_exit_code "nonexistent path fails closed" "$UNREADABLE" 2

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "FAILURES:"
  for _e in "${ERRORS[@]}"; do
    echo "  - $_e"
  done
  echo ""
  echo "scripts/qc-check-whatsapp-json.py must fail CLOSED (exit 2) on"
  echo "malformed/unreadable non-empty JSON — never exit 0 (silently waved"
  echo "through) or crash uncaught. See the script's own docstring."
  exit 1
fi

echo "All qc-check-whatsapp-json.py exit-code contract checks passed."
exit 0
