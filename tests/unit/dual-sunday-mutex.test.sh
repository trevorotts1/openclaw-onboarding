#!/usr/bin/env bash
# tests/unit/dual-sunday-mutex.test.sh — U001 regression lock
# Mutation targets: update-skills.sh:1608 (flock -n) and :1683 (retirement grep -E).
# FIXER PASS: fixer-transcript-004 hollow test + behavioral probes.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
_pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

# -------------------------------------------------------------------
# Pre-flight
# -------------------------------------------------------------------
_section "T0 — bash -n"
bash -n "$TARGET" && _pass "update-skills.sh passes bash -n" || { _fail "bash -n failed"; exit 2; }

# -------------------------------------------------------------------
# Static pattern checks (keep existing, fix T4)
# -------------------------------------------------------------------
_section "T1 — lock functions"
grep -q 'acquire_update_lock()' "$TARGET" && _pass "acquire_update_lock defined" || _fail "acquire_update_lock NOT found"
grep -q 'release_update_lock()' "$TARGET" && _pass "release_update_lock defined" || _fail "release_update_lock NOT found"

_section "T2 — MUTATION TARGET: flock -n guard"
grep -q 'flock -n.*UPDATE_LOCK_FD' "$TARGET" && _pass "flock -n guard present (line ~1608 — mutate to no-op -> RED)" || _fail "flock -n guard NOT found"

_section "T3 — crontab functions"
grep -q 'detect_legacy_sunday_crontab()' "$TARGET" && _pass "detect_legacy defined" || _fail "detect_legacy NOT found"
grep -q 'retire_legacy_sunday_crontab()' "$TARGET" && _pass "retire_legacy defined" || _fail "retire_legacy NOT found"

# ── T4 — MUTATION TARGET: retirement grep -Ev (line 1683 ONLY) ────────────────
# The OLD pattern `grep -E.*0.*3.*\*.*\*` matched BOTH :1656 (detect grep -Eq)
# AND :1683 (retire grep -Ev). When :1683 was no-opped to `grep -Ev 'NOMATCH-PROBE'`,
# the old T4 stayed GREEN — the suite could not detect a broken retirement filter.
# Fix: match uniquely on `grep -Ev` which appears ONLY at line 1683 in the
# entire script. Also anchor to '"$backup"' to double-proof the exact line.
_section "T4 — MUTATION TARGET: retirement grep -Ev (line 1683, unique)"
GREP_EV_COUNT=$(grep -c 'grep -Ev' "$TARGET" 2>/dev/null || echo "0")
if [ "$GREP_EV_COUNT" -eq 1 ]; then
  _pass "exactly one grep -Ev in update-skills.sh (line 1683 — mutation target)"
else
  _fail "expected exactly one grep -Ev (line 1683); found ${GREP_EV_COUNT} — T4 cannot uniquely target the retirement filter"
fi
grep -q 'grep -Ev.*0|7|0,6.*"\$backup"' "$TARGET" && _pass "retirement grep -Ev filter present with \"\$backup\" anchor (line ~1683 — mutate to NOMATCH-PROBE -> RED)" || _fail "retirement grep -Ev filter NOT found with unique anchor"

_section "T5 — Sunday variant coverage"
grep -q '0|7|0,6' "$TARGET" && _pass "Sunday matcher covers 0, 7, and 0,6" || _fail "Sunday matcher NOT widened"

_section "T6 — env failure distinct from contention"
grep -q 'FATAL: cannot create lock' "$TARGET" && _pass "FATAL lock-create message present" || _fail "FATAL lock-create message NOT found"

_section "T7 — trap wired"
grep -q 'trap release_update_lock EXIT' "$TARGET" && _pass "release trap wired in main()" || _fail "release trap NOT wired"

_section "T8 — retirement messages"
grep -q 'RETIRED.*legacy Sunday' "$TARGET" && grep -q 'OWNER NOTICE' "$TARGET" && _pass "retirement prints RETIRED + OWNER NOTICE" || _fail "retirement messages missing"

_section "T9 — install failure preserves original"
grep -q 'original.*intact\|failed to reinstall' "$TARGET" && _pass "install failure preserves original" || _fail "original-intact NOT found"

_section "T10 — acquire_lock first in main()"
MAIN_LINE=$(grep -n '^main()' "$TARGET" | head -1 | cut -d: -f1)
if [ -n "$MAIN_LINE" ]; then
  BLOCK=$(tail -n +"$MAIN_LINE" "$TARGET" | head -25)
  echo "$BLOCK" | grep -q 'acquire_update_lock' && _pass "acquire_update_lock is first action in main()" || _fail "acquire_update_lock NOT first in main()"
else
  _fail "main() not found"
fi

# -------------------------------------------------------------------
# BEHAVIORAL TESTS — sandboxed with fake HOME + fake crontab on PATH
# -------------------------------------------------------------------

# Shared sandbox helpers
_sandbox_setup() {
  TESTHOME="$(mktemp -d)"
  FAKEBIN="$TESTHOME/bin"
  mkdir -p "$FAKEBIN"
  _SANDBOX_TARGET="$TARGET"
}

_sandbox_install_fake_crontab() {
  # $1: initial crontab content (multi-line string)
  local content="$1"
  printf '%b' "$content" > "$TESTHOME/.fake-crontab"
  cat > "$FAKEBIN/crontab" <<'FAKECRON'
#!/usr/bin/env bash
C_FILE="${HOME}/.fake-crontab"
if [ "$1" = "-l" ]; then
  cat "$C_FILE" 2>/dev/null
  exit 0
fi
# A filename argument means "install this as the new crontab"
cp "$1" "$C_FILE"
exit 0
FAKECRON
  chmod +x "$FAKEBIN/crontab"
}

_sandbox_run_script() {
  # Run update-skills.sh inside the sandbox. Captures stdout+stderr, returns rc.
  # Args forwarded to update-skills.sh (e.g. --help).
  HOME="$TESTHOME" \
  PATH="$FAKEBIN:$PATH" \
  OPENCLAW_UPDATE_SKIP_SELF_SYNC=1 \
    bash "$_SANDBOX_TARGET" "$@" 2>&1
}

_sandbox_crontab_l() {
  HOME="$TESTHOME" PATH="$FAKEBIN:$PATH" crontab -l 2>/dev/null
}

_sandbox_teardown() {
  rm -rf "$TESTHOME" 2>/dev/null || true
}

# T4b — Behavioral retirement filter: prove the filter ACTUALLY removes │
# a `0 3 * * 0` line from the crontab and creates a proper backup.      │
# If :1683 is mutated to `grep -Ev 'NOMATCH-PROBE'`, the Sunday line    │
# survives in the crontab post-run and this test goes RED.              │
_section "T4b — BEHAVIORAL: retirement filter removes Sunday line + creates backup"
_sandbox_setup
_sandbox_install_fake_crontab "0 3 * * 0 /usr/bin/some-legacy-cmd\n# a comment\n30 2 * * * /usr/bin/other\n"
T4B_OUT="$(_sandbox_run_script --help)"
T4B_RC=$?

# After retirement, the Sunday line must be GONE from current crontab store
T4B_POST="$(_sandbox_crontab_l)"
if echo "$T4B_POST" | grep -q '0 3 \* \* 0'; then
  _fail "T4b: Sunday line 0 3 * * 0 STILL PRESENT in crontab after retirement (filter did NOT remove it)"
elif [ "$T4B_RC" -eq 0 ]; then
  _pass "T4b: Sunday line removed from crontab store (retirement filter worked)"
else
  _fail "T4b: script exited $T4B_RC instead of 0: $T4B_OUT"
fi

# Backup file must exist and contain the original Sunday line
T4B_BAK=$(ls "$TESTHOME"/.crontab.bak-dual-sunday-* 2>/dev/null | head -1)
if [ -z "$T4B_BAK" ]; then
  _fail "T4b: no backup file created at .crontab.bak-dual-sunday-*"
else
  if grep -q '0 3 \* \* 0' "$T4B_BAK"; then
    _pass "T4b: backup file contains the retired Sunday line"
  else
    _fail "T4b: backup file $T4B_BAK does NOT contain the Sunday line"
  fi
fi

# Output must include RETIRED message (proves the code path ran)
if echo "$T4B_OUT" | grep -q "RETIRED.*legacy Sunday"; then
  _pass "T4b: output contains 'RETIRED legacy Sunday' retirement message"
else
  _fail "T4b: output missing 'RETIRED legacy Sunday' — retirement code path did not execute"
fi

_sandbox_teardown

# T4c — Behavioral: no-op when no Sunday line present (smoke test)
_section "T4c — BEHAVIORAL: retirement is silent no-op when crontab has no Sunday line"
_sandbox_setup
_sandbox_install_fake_crontab "30 2 * * * /usr/bin/other\n# just a comment\n"
T4C_OUT="$(_sandbox_run_script --help)"
T4C_RC=$?
T4C_POST="$(_sandbox_crontab_l)"
if [ "$T4C_RC" -eq 0 ] && echo "$T4C_OUT" | grep -q "no legacy Sunday.*nothing to retire"; then
  _pass "T4c: no Sunday line → nothing to retire, crontab unchanged"
else
  _fail "T4c: expected no-op with 'nothing to retire' message, got rc=$T4C_RC: $T4C_OUT"
fi
# Crontab must be byte-identical post-run
if [ "$T4C_POST" = "$(printf '30 2 * * * /usr/bin/other\n# just a comment\n')" ]; then
  _pass "T4c: crontab byte-identical after no-op retirement run"
else
  _fail "T4c: crontab content changed during no-op run: got [$T4C_POST]"
fi
_sandbox_teardown

# T4d — Behavioral: Sunday variant 7 (0|7|0,6 coverage)
_section "T4d — BEHAVIORAL: Sunday field '7' (0|7|0,6 variant) also retired"
_sandbox_setup
_sandbox_install_fake_crontab "0 3 * * 7 /usr/bin/cmd-seven\n"
T4D_OUT="$(_sandbox_run_script --help)"
T4D_RC=$?
T4D_POST="$(_sandbox_crontab_l)"
if [ "$T4D_RC" -eq 0 ] && ! echo "$T4D_POST" | grep -q '0 3 \* \* 7'; then
  _pass "T4d: Sunday field '7' was detected and retired"
else
  _fail "T4d: Sunday field '7' was NOT retired (rc=$T4D_RC): $T4D_OUT"
fi
_sandbox_teardown

# T4e — Behavioral: Sunday variant 0,6 (0|7|0,6 coverage)
_section "T4e — BEHAVIORAL: Sunday field '0,6' variant also retired"
_sandbox_setup
_sandbox_install_fake_crontab "0 3 * * 0,6 /usr/bin/cmd-06\n"
T4E_OUT="$(_sandbox_run_script --help)"
T4E_RC=$?
T4E_POST="$(_sandbox_crontab_l)"
if [ "$T4E_RC" -eq 0 ] && ! echo "$T4E_POST" | grep -q '0 3 \* \* 0,6'; then
  _pass "T4e: Sunday field '0,6' was detected and retired"
else
  _fail "T4e: Sunday field '0,6' was NOT retired (rc=$T4E_RC): $T4E_OUT"
fi
_sandbox_teardown

# TLOCK — Behavioral lock test: hold lock dir with live pid,                  │
# invoke --help, assert exit 1 + "LOCK HELD" + zero update output.           │
# Tests that a concurrent run is properly blocked at the mutex.              │
_section "TLOCK — BEHAVIORAL: lock held by live pid blocks execution with exit 1"

LOCK_PATH="/tmp/openclaw-update.lock"
LOCK_EXISTED=0

# Save any pre-existing lock
if [ -d "$LOCK_PATH" ]; then
  LOCK_EXISTED=1
  LOCK_SAVED="$(mktemp -d /tmp/openclaw-update.lock-saved.XXXXXX)"
  cp -a "$LOCK_PATH"/* "$LOCK_SAVED/" 2>/dev/null || true
  rm -rf "$LOCK_PATH"
fi

# Create lock directory with our own PID (alive → LOCK HELD)
mkdir -p "$LOCK_PATH"
echo "$$" > "$LOCK_PATH/pid"

TLOCK_OUT="$(_sandbox_setup; _sandbox_install_fake_crontab ""; _sandbox_run_script --help)"
TLOCK_RC=$?
rm -rf "$LOCK_PATH"

# Restore if we saved
if [ "$LOCK_EXISTED" -eq 1 ] && [ -n "${LOCK_SAVED:-}" ]; then
  mkdir -p "$LOCK_PATH"
  cp -a "$LOCK_SAVED"/* "$LOCK_PATH/" 2>/dev/null || true
  rm -rf "$LOCK_SAVED"
fi

if [ "$TLOCK_RC" -eq 1 ]; then
  _pass "TLOCK: lock held by live pid → exit 1"
else
  _fail "TLOCK: expected exit 1 with locked mutex, got $TLOCK_RC: $TLOCK_OUT"
fi

if echo "$TLOCK_OUT" | grep -q "LOCK HELD"; then
  _pass "TLOCK: output contains 'LOCK HELD'"
else
  _fail "TLOCK: output missing 'LOCK HELD': $TLOCK_OUT"
fi

# Zero update output: must NOT contain usage text (proves script never reached --help)
if echo "$TLOCK_OUT" | grep -q "Usage: update-skills.sh"; then
  _fail "TLOCK: script reached --help usage text despite held lock — execution leaked past mutex"
else
  _pass "TLOCK: no update/usage output — execution stopped at mutex"
fi

_sandbox_teardown 2>/dev/null || true

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""; echo "=========================================="
echo "  PASS: $PASS  FAIL: $FAIL"
echo "=========================================="
[ "$FAIL" -eq 0 ] || exit 1
