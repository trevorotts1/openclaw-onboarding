#!/usr/bin/env bash
# tests/unit/scrub-operator-chat-id.test.sh
#
# Locks scripts/scrub-operator-chat-id.py, the guard that keeps the operator's
# personal Telegram chat id out of agent-facing, client-installed files.
#
# Fixtures (tests/fixtures/scrub-operator-chat-id/):
#   fix-case/cron-prompt.txt     agent-facing file carrying the literal  -> FIX
#   keep-case/tests/guard.txt    test asserting the id must not leak     -> KEEP
#
# Asserts:
#   (1) --check on the FIX fixture exits 1 and names the file.
#   (2) --check on the KEEP fixture exits 0.
#   (3) --report exits 0 and labels the fixture lines FIX / KEEP.
#   (4) --check on the real repo exits 0 (nothing agent-facing carries the id).
#   (5) --apply on the real repo is a no-op (idempotent: rewrites 0 files).
#   (6) --check sees every resolver-declared operator id, not only the primary literal.
#
# HERMETIC: no network, no openclaw, no client box. Writes nothing in the repo.
#
# Exit 0 = all checks pass. Exit 1 = a regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/scrub-operator-chat-id.py"
FIXT="$REPO_ROOT/tests/fixtures/scrub-operator-chat-id"

PASS=0; FAIL=0
pass() { printf "  PASS: %s\n" "$1"; PASS=$((PASS+1)); }
fail() { printf "  FAIL: %s\n" "$1"; FAIL=$((FAIL+1)); }

echo "=== scrub-operator-chat-id.test.sh ==="

[ -f "$SCRIPT" ] || { fail "scripts/scrub-operator-chat-id.py missing"; exit 1; }

out="$(python3 "$SCRIPT" --check --root "$FIXT/fix-case" 2>&1)"; rc=$?
if [ "$rc" = "1" ] && grep -q 'cron-prompt.txt:2' <<<"$out"; then
  pass "1: --check on the FIX fixture exits 1 and names cron-prompt.txt:2"
else
  fail "1: FIX fixture should exit 1 naming cron-prompt.txt:2 (rc=$rc)"
fi

out="$(python3 "$SCRIPT" --check --root "$FIXT/keep-case" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  pass "2: --check on the KEEP fixture exits 0"
else
  fail "2: KEEP fixture should exit 0 (rc=$rc): $out"
fi

fix_rep="$(python3 "$SCRIPT" --report --root "$FIXT/fix-case" 2>&1)"; r1=$?
keep_rep="$(python3 "$SCRIPT" --report --root "$FIXT/keep-case" 2>&1)"; r2=$?
if [ "$r1" = "0" ] && [ "$r2" = "0" ] \
   && grep -q '^FIX .*cron-prompt.txt:2' <<<"$fix_rep" \
   && grep -q '^KEEP .*tests/guard.txt:2' <<<"$keep_rep"; then
  pass "3: --report exits 0 and labels FIX and KEEP lines"
else
  fail "3: --report did not label the fixtures FIX / KEEP (rc=$r1/$r2)"
fi

out="$(python3 "$SCRIPT" --check --root "$REPO_ROOT" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  pass "4: --check on the real repo exits 0"
else
  fail "4: a FIX-class occurrence exists in the repo (rc=$rc): $out"
fi

out="$(python3 "$SCRIPT" --apply --root "$REPO_ROOT" 2>&1)"; rc=$?
if [ "$rc" = "0" ] && grep -q 'files rewritten: 0' <<<"$out"; then
  pass "5: --apply on the real repo is idempotent (0 files rewritten)"
else
  fail "5: --apply was not a no-op on the real repo (rc=$rc): $out"
fi

# 6: the guard must scan EVERY operator id declared by the single authority
#    (shared-utils/resolve-owner-chat.sh), not only the primary literal.
TMP6="$(mktemp -d)"; trap 'rm -rf "$TMP6"' EXIT
mkdir -p "$TMP6/fixcase"
ID2="$(python3 - "$REPO_ROOT/shared-utils/resolve-owner-chat.sh" <<'PY'
import re, sys
try:
    ids = re.findall(r'OPERATOR_CHAT_IDS_SH="([^"]*)"', open(sys.argv[1]).read())[0].split()
except Exception:
    ids = []
print(ids[1] if len(ids) > 1 else "")
PY
)"
if [ -n "$ID2" ]; then
  printf 'agent-facing shadow fixture: chat %s hardcoded\n' "$ID2" > "$TMP6/fixcase/cron-prompt.txt"
  out="$(python3 "$SCRIPT" --check --root "$TMP6/fixcase" 2>&1)"; rc=$?
  if [ "$rc" = "1" ] && grep -q 'cron-prompt.txt:1' <<<"$out"; then
    pass "6: guard sees operator id 2 declared by the resolver, not only the primary literal"
  else
    fail "6: resolver-declared id 2 payload was invisible to the guard (rc=$rc)"
  fi
else
  fail "6: could not extract a second operator id from resolve-owner-chat.sh"
fi

echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
