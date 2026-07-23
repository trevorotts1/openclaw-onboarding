#!/usr/bin/env bash
# tests/unit/skill35-cron-schedule-comparison.test.sh
#
# U129 — the Skill 35 weekly-theme cron registrar must compare the SCHEDULE of an
# existing entry, not just its row count and session target.
#
# THE BUG THIS GUARDS AGAINST: register-weekly-cron.sh's dedup check counted rows
# and confirmed sessionTarget=main, but never compared the cron expression. An
# existing job scheduled for the WRONG day (e.g. Monday "0 8 * * 1") satisfied
# both checks, so the registrar reported "already registered … nothing to do" and
# the weekly cycle silently ran on the wrong day.
#
# THE FIX: parse the 5-field schedule out of the existing row and compare it to
# the intended expression ("0 8 * * 6", Saturday 8 AM). Any mismatch falls through
# to delete + re-register.
#
# Tests (hermetic: a fake `openclaw` on PATH whose `cron list` output is driven by
# env vars; no real gateway, no network):
#   T1  existing entry on the CORRECT schedule + main target -> "nothing to do", exit 0,
#       and NO re-registration (cron add never called)
#   T2  existing entry on the WRONG schedule + main target -> re-registers (cron add
#       called) — THE FIX: a wrong-day job is no longer reported healthy
#   T3  whitespace-variant of the correct schedule ("0  8 * * 6") still counts as a
#       match (normalization), so a healthy entry is not needlessly re-registered
#   T4  MUTATION PROOF: drop the schedule comparison from the healthy check -> the
#       wrong-schedule entry of T2 is reported healthy (RED); revert -> re-registers (GREEN)
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REG="$REPO_ROOT/35-social-media-planner/scripts/register-weekly-cron.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== skill35-cron-schedule-comparison.test.sh ==="
[ -f "$REG" ] || { echo "FAIL: registrar not found at $REG"; exit 1; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/u129-XXXXXX")"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT

# A fake `openclaw`. `cron list` prints $FAKE_CRON_LIST; `cron add` records that it
# was called; `cron delete` and `config validate` succeed silently.
BIN="$SANDBOX/bin"; mkdir -p "$BIN"
ADD_LOG="$SANDBOX/cron-add-calls"
: > "$ADD_LOG"
cat > "$BIN/openclaw" <<'OC'
#!/usr/bin/env bash
case "${1:-} ${2:-}" in
  "cron list")   printf '%s\n' "${FAKE_CRON_LIST:-}"; exit 0 ;;
  "cron add")    echo "add $*" >> "$ADD_LOG_PATH"; exit 0 ;;
  "cron delete") exit 0 ;;
  "config validate") exit 0 ;;
esac
exit 0
OC
chmod +x "$BIN/openclaw"

_run() { # <extra-env...> -> runs the registrar with a clean environment
  env -i HOME="$SANDBOX/home" PATH="$BIN:/usr/local/bin:/usr/bin:/bin" \
    ADD_LOG_PATH="$ADD_LOG" "$@" bash "$REG" 2>&1
}
mkdir -p "$SANDBOX/home"

# A cron-list row for the skill35 weekly-theme entry. $1 = schedule expression.
_row() { printf 'id=11111111-2222-3333-4444-555555555555 name=skill35-weekly-theme cron=%s sessionTarget=main\n' "$1"; }

echo ""
echo "--- T1: existing entry on the CORRECT schedule is left alone ---"
: > "$ADD_LOG"
OUT1="$(_run FAKE_CRON_LIST="$(_row '0 8 * * 6')")"; rc1=$?
if [ "$rc1" -eq 0 ] && printf '%s' "$OUT1" | grep -q "nothing to do"; then
  pass "T1: correct schedule + main target -> 'nothing to do' (exit 0)"
else
  fail "T1: expected 'nothing to do' exit 0 (rc=$rc1)"; printf '%s\n' "$OUT1" | sed 's/^/      /'
fi
if [ -s "$ADD_LOG" ]; then
  fail "T1: a healthy correct-schedule entry was needlessly re-registered (cron add called)"
else
  pass "T1: no re-registration for a healthy correct-schedule entry"
fi

echo ""
echo "--- T2: existing entry on the WRONG schedule is re-registered (THE FIX) ---"
: > "$ADD_LOG"
OUT2="$(_run FAKE_CRON_LIST="$(_row '0 8 * * 1')")"; rc2=$?
if [ -s "$ADD_LOG" ]; then
  pass "T2: a wrong-schedule (Monday) entry triggers delete + re-register (cron add called)"
else
  fail "T2: a wrong-schedule entry was NOT re-registered — the bug (reported healthy)"
  printf '%s\n' "$OUT2" | sed 's/^/      /'
fi
if printf '%s' "$OUT2" | grep -q "expected '0 8 \* \* 6'"; then
  pass "T2: the registrar names the schedule mismatch in its notice"
else
  fail "T2: no schedule-mismatch notice was printed"; printf '%s\n' "$OUT2" | sed 's/^/      /'
fi

echo ""
echo "--- T3: a whitespace-variant of the correct schedule still matches ---"
: > "$ADD_LOG"
OUT3="$(_run FAKE_CRON_LIST="$(_row '0  8 * * 6')")"; rc3=$?
if [ "$rc3" -eq 0 ] && printf '%s' "$OUT3" | grep -q "nothing to do" && [ ! -s "$ADD_LOG" ]; then
  pass "T3: '0  8 * * 6' (extra space) is normalized to a match -> not re-registered"
else
  fail "T3: a whitespace-variant of the correct schedule was needlessly re-registered (rc=$rc3)"
  printf '%s\n' "$OUT3" | sed 's/^/      /'
fi

echo ""
echo "--- T4: MUTATION PROOF — drop the schedule comparison ---"
MUT="$SANDBOX/register.MUTATED.sh"
python3 - "$REG" "$MUT" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
# Remove the schedule comparison from the healthy-entry condition, restoring the
# pre-fix shape (row count + main target only).
needle = 'if [ "$_is_main" -ge 1 ] && [ "$_is_error" -eq 0 ] && [ "$_existing_norm" = "$_intended_norm" ]; then'
repl   = 'if [ "$_is_main" -ge 1 ] && [ "$_is_error" -eq 0 ]; then'
assert needle in s, "mutation target not found"
open(dst, "w").write(s.replace(needle, repl))
PY
: > "$ADD_LOG"
OUT4="$(env -i HOME="$SANDBOX/home" PATH="$BIN:/usr/local/bin:/usr/bin:/bin" \
  ADD_LOG_PATH="$ADD_LOG" FAKE_CRON_LIST="$(_row '0 8 * * 1')" bash "$MUT" 2>&1)"; rc4=$?
if [ ! -s "$ADD_LOG" ] && printf '%s' "$OUT4" | grep -q "nothing to do"; then
  pass "T4 RED: with the schedule comparison removed, a wrong-day entry is reported healthy (bug reproduced)"
else
  fail "T4 RED: mutation did not reproduce the bug (the wrong-day entry was still re-registered)"
  printf '%s\n' "$OUT4" | sed 's/^/      /'
fi
# GREEN: the real (unmutated) script re-registers the same wrong-day entry.
: > "$ADD_LOG"
OUT4b="$(_run FAKE_CRON_LIST="$(_row '0 8 * * 1')")"
if [ -s "$ADD_LOG" ]; then
  pass "T4 GREEN: the real script re-registers the wrong-day entry (fix restored)"
else
  fail "T4 GREEN: the real script did not re-register the wrong-day entry"
  printf '%s\n' "$OUT4b" | sed 's/^/      /'
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && { echo "FAIL: $FAIL check(s) failed — CI guard triggered"; exit 1; }
echo "PASS: the Skill 35 cron registrar compares the schedule, not just the row count"
exit 0
