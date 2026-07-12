#!/usr/bin/env bash
# ============================================================
#  test-p107-sunday-update-probe.sh — P1-07 (c)3 regression lock
#
#  Proves scripts/probe/p107-sunday-update-probe.sh does EXACT
#  schedule+command matching against crontab -l, never a truncated-text
#  grep (the v19.47.0 lesson this probe exists to avoid repeating).
#
#  Every scenario below stubs `crontab` with a fake implementation on PATH
#  so this test NEVER reads or writes the real system crontab.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/probe/p107-sunday-update-probe.sh"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

TESTHOME="$(mktemp -d)"
FAKEBIN="$TESTHOME/bin"
mkdir -p "$FAKEBIN" "$TESTHOME/.openclaw/skills"
trap 'rm -rf "$TESTHOME"' EXIT

SUNDAY_CMD="$TESTHOME/.openclaw/skills/.update-restart-if-needed"
SATURDAY_CMD="$TESTHOME/.openclaw/skills/.openclaw-self-update"

# _install_fake_crontab <content-or-empty>
_install_fake_crontab() {
  local content="$1"
  printf '%s\n' "$content" > "$TESTHOME/.fake-crontab"
  cat > "$FAKEBIN/crontab" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "-l" ]; then
  cat "$TESTHOME/.fake-crontab"
  exit 0
fi
exit 0
EOF
  chmod +x "$FAKEBIN/crontab"
}

_run_probe() {
  HOME="$TESTHOME" PATH="$FAKEBIN:$PATH" bash "$PROBE" "$@"
}

# ─── Scenario 1: empty crontab — pre-fix behaviour class (never installed) ──
_section "Scenario 1 — empty crontab must report MISS for both crons, exit 1"
_install_fake_crontab ""
OUT="$(_run_probe 2>&1)"; RC=$?
if [ "$RC" -eq 1 ] && echo "$OUT" | grep -q "\[MISS\].*Sunday" && echo "$OUT" | grep -q "\[MISS\].*Saturday"; then
  _pass "empty crontab -> MISS/MISS, exit 1"
else
  _fail "empty crontab did not report MISS/MISS exit 1 (rc=$RC): $OUT"
fi

# ─── Scenario 2: exact canonical lines present — must report OK/OK, exit 0 ──
_section "Scenario 2 — exact canonical lines present must report ARMED, exit 0"
_install_fake_crontab "0 3 * * 0 $SUNDAY_CMD
59 23 * * 6 $SATURDAY_CMD"
OUT="$(_run_probe 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && echo "$OUT" | grep -q "VERDICT: ARMED"; then
  _pass "exact canonical lines -> ARMED, exit 0"
else
  _fail "exact canonical lines did not report ARMED exit 0 (rc=$RC): $OUT"
fi

# ─── Scenario 3: THE BUG CLASS — a line that would false-positive under a
# substring grep (e.g. `grep -q "update-restart-if-needed"`) but is NOT the
# canonical schedule (wrong hour) must still be reported MISS. This is the
# exact failure mode the old setup-weekly-update.sh add-or-skip check (a
# truncated-text grep) could not distinguish, and is the fail-first proof
# this probe's exact-match logic actually fixes it. ───────────────────────
_section "Scenario 3 — wrong-schedule line must be MISS despite command substring matching (proves no grep-substring false positive)"
_install_fake_crontab "0 5 * * 0 $SUNDAY_CMD --some-extra-flag-a-substring-grep-would-still-match
59 23 * * 6 $SATURDAY_CMD"
OUT="$(_run_probe 2>&1)"; RC=$?
if [ "$RC" -eq 1 ] && echo "$OUT" | grep -q "\[MISS\].*Sunday"; then
  _pass "wrong-schedule/extra-args Sunday line correctly reported MISS (exact match, not substring)"
else
  _fail "wrong-schedule Sunday line was NOT reported as MISS — exact-match regressed to substring behaviour (rc=$RC): $OUT"
fi

# Cross-check: a plain grep -qF over the SAME crontab WOULD have wrongly
# reported present, demonstrating why the exact-match rewrite matters.
# (Both invocations below are pinned to the FAKE crontab binary — this test
# must never read or write the real system crontab.)
if HOME="$TESTHOME" PATH="$FAKEBIN:$PATH" crontab -l 2>/dev/null | grep -qF "$SUNDAY_CMD"; then
  _pass "control: naive substring grep DOES false-positive on scenario 3 (confirms the probe is testing the real bug class)"
else
  _fail "control: naive substring grep unexpectedly did not match scenario 3 — test fixture is not exercising the intended bug class"
fi

# ─── Scenario 4: --json emits well-formed JSON with the expected keys ──────
_section "Scenario 4 — --json output is valid JSON with expected keys"
_install_fake_crontab ""
OUT="$(_run_probe --json 2>&1)"; RC=$?
if echo "$OUT" | python3 -c "
import json,sys
d = json.load(sys.stdin)
assert d['sunday_cron_present'] is False
assert d['saturday_cron_present'] is False
assert d['overall_armed'] is False
assert 'box' in d and 'checked_at' in d
" 2>/dev/null; then
  _pass "--json emits valid JSON with expected keys/values for the MISS case"
else
  _fail "--json output malformed or missing expected keys: $OUT"
fi

# ─── Scenario 5: --remediate installs the missing crons via the real
# setup-weekly-update.sh (still fully sandboxed — fake HOME, fake crontab
# binary that WRITES to the fake file so we can observe the install) ───────
_section "Scenario 5 — --remediate installs missing crons and the re-check reports ARMED"
_install_fake_crontab ""
cat > "$FAKEBIN/crontab" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "-l" ]; then
  cat "$TESTHOME/.fake-crontab" 2>/dev/null
  exit 0
fi
# setup-weekly-update.sh pipes: (crontab -l; echo "...") | crontab -
cat > "$TESTHOME/.fake-crontab.new"
cat "$TESTHOME/.fake-crontab.new" >> "$TESTHOME/.fake-crontab" 2>/dev/null || cp "$TESTHOME/.fake-crontab.new" "$TESTHOME/.fake-crontab"
exit 0
EOF
chmod +x "$FAKEBIN/crontab"
OUT="$(_run_probe --remediate 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && echo "$OUT" | grep -q "VERDICT: ARMED" && echo "$OUT" | grep -q "\-\-remediate ran"; then
  _pass "--remediate installed both crons and re-check reports ARMED"
else
  _fail "--remediate did not converge to ARMED (rc=$RC): $OUT"
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0
