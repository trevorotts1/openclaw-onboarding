#!/usr/bin/env bash
# selftest-qc-assert.sh — hermetic self-test for scripts/qc-assert-no-client-names.sh
#
# Proves the externalized client-name gate still BITES, WITHOUT depending on the
# operator's real roster and WITHOUT shipping any real client name:
#
#   1. Build a throwaway temp "repo" containing the planted fixture (which holds
#      the placeholder sentinel "Testclient Sentinel") copied to a NON-excluded
#      path, plus a temp roster listing exactly that sentinel.
#   2. Point $OPENCLAW_CLIENT_ROSTER at the temp roster and run the gate against
#      the temp repo → expect exit 1 (detector fires on a known roster name).
#   3. Remove the leak, leave only tokenized clean content → expect exit 0.
#
# The temp roster contains a placeholder, never a real client. Run:
#   bash tests/fixtures/no-client-names/selftest-qc-assert.sh
#
# Exit 0 = self-test passed; 1 = self-test failed.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
GATE="$REPO_ROOT/scripts/qc-assert-no-client-names.sh"
FIXTURE="$HERE/planted-client-name.txt"
EXAMPLE_ROSTER="$REPO_ROOT/scripts/client-roster.example.txt"

fail() { echo "  [SELFTEST FAIL] $1" >&2; exit 1; }

[ -f "$GATE" ]           || fail "gate not found at $GATE"
[ -f "$FIXTURE" ]        || fail "planted fixture not found at $FIXTURE"
[ -f "$EXAMPLE_ROSTER" ] || fail "roster template not found at $EXAMPLE_ROSTER"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# A temp roster with exactly the placeholder sentinel (no real client name). Use
# the committed .example so the test also proves the shipped template is usable.
ROSTER="$TMP/roster.txt"
cp "$EXAMPLE_ROSTER" "$ROSTER"

# ── Case 1: planted placeholder name IS detected (gate must exit non-zero) ──────
LEAKREPO="$TMP/leakrepo"
mkdir -p "$LEAKREPO"
# Copy the fixture to a path the gate does NOT self-exclude so it is scanned.
cp "$FIXTURE" "$LEAKREPO/leaked-content.txt"
set +e
OPENCLAW_CLIENT_ROSTER="$ROSTER" bash "$GATE" --repo-root "$LEAKREPO" >"$TMP/leak.out" 2>&1
rc_leak=$?
set -e
if [ "$rc_leak" -eq 0 ]; then
  cat "$TMP/leak.out" >&2
  fail "gate PASSED on a repo containing a known roster name (should exit 1)"
fi
echo "  [SELFTEST ok] gate detected the planted placeholder name (exit $rc_leak)"

# ── Case 2: clean tokenized content passes (gate must exit zero) ────────────────
CLEANREPO="$TMP/cleanrepo"
mkdir -p "$CLEANREPO"
printf 'Owner: {{ownerName}}\nCompany: {{companyName}}\nA client VPS box.\n' \
  > "$CLEANREPO/clean.txt"
set +e
OPENCLAW_CLIENT_ROSTER="$ROSTER" bash "$GATE" --repo-root "$CLEANREPO" >"$TMP/clean.out" 2>&1
rc_clean=$?
set -e
if [ "$rc_clean" -ne 0 ]; then
  cat "$TMP/clean.out" >&2
  fail "gate FAILED on clean tokenized content (should exit 0)"
fi
echo "  [SELFTEST ok] gate passed on clean tokenized content (exit $rc_clean)"

echo "[selftest-qc-assert] PASS — externalized gate bites on a known name and passes clean content."
exit 0
