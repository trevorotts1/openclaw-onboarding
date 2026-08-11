#!/usr/bin/env bash
# tests/unit/onboarding-resume-guard-sees-disabled.test.sh
#
# Regression test: lib-onboarding-resume-cron.sh's idempotency guard must use
# `openclaw cron list --all`, not bare `openclaw cron list`. `cron list` HIDES
# DISABLED JOBS (--all defaults to false). Without --all the guard cannot see a
# cron an operator deliberately disabled, so every roll re-creates it ENABLED
# and re-arms the */30 main-session self-ping loop. Reproduced on four boxes:
# `cron list` -> 0 matches, `cron list --all` -> 1 match.
#
# Assertion groups:
#   (1) DETECTS_DISABLED -- with a stub openclaw on PATH where `cron list --all`
#                           shows a disabled onboarding-resume job and plain
#                           `cron list` shows nothing, the guard's exact command
#                           form (`cron list --all | grep -qi ...`) detects it,
#                           and the pre-fix form (bare `cron list | grep -qi
#                           ...`) does NOT -- proving this is the real
#                           regression, not a stylistic diff.
#   (2) HAS_ALL_FLAG      -- the literal string `cron list --all` is present in
#                           lib-onboarding-resume-cron.sh
#   (3) FAIL_CLOSED       -- the specific idempotency-guard line (the one that
#                           greps for "onboarding-resume") itself uses --all;
#                           a revert to bare `cron list` fails this check even
#                           if --all still appears elsewhere in the file (e.g.
#                           only in a comment)
#
# Hermetic: a fake `openclaw` on PATH in a scratch temp dir. No live gateway,
# no real cron store, is touched.
#
# Run: bash tests/unit/onboarding-resume-guard-sees-disabled.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESUME_CRON_LIB="$REPO_ROOT/lib-onboarding-resume-cron.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== onboarding-resume-guard-sees-disabled.test.sh ==="
echo ""

if [[ ! -f "$RESUME_CRON_LIB" ]]; then
  echo "FATAL: lib-onboarding-resume-cron.sh not found at $RESUME_CRON_LIB" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# (1) DETECTS_DISABLED: stub openclaw -- `cron list --all` shows a disabled
#     onboarding-resume job, plain `cron list` shows nothing (matches live
#     openclaw behaviour: --all defaults to false and hides disabled jobs).
# ---------------------------------------------------------------------------
echo "--- (1) DETECTS_DISABLED: guard command form sees a disabled cron ---"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/onboarding-resume-guard.XXXXXX")"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

mkdir -p "$SANDBOX/bin"
cat > "$SANDBOX/bin/openclaw" <<'STUBEOF'
#!/usr/bin/env bash
# Stub openclaw for this test only. Emulates the one behaviour this guard
# depends on: `cron list --all` shows disabled jobs, plain `cron list` does not.
if [ "${1:-}" = "cron" ] && [ "${2:-}" = "list" ]; then
  shift 2
  for _a in "$@"; do
    if [ "$_a" = "--all" ]; then
      echo "job-9f2  onboarding-resume  enabled=false  */30 * * * *"
      exit 0
    fi
  done
  # No --all: live openclaw hides disabled jobs here. Emit nothing.
  exit 0
fi
exit 0
STUBEOF
chmod +x "$SANDBOX/bin/openclaw"

STUB_PATH="$SANDBOX/bin:/usr/bin:/bin"

# The guard's ACTUAL post-fix command form -- the literal pipeline that lives
# in the source file, not a re-implementation of its logic.
if PATH="$STUB_PATH" bash -c 'openclaw cron list --all 2>/dev/null | grep -qi "onboarding-resume"'; then
  pass "1a: 'cron list --all | grep -qi onboarding-resume' detects a disabled job"
else
  fail "1a: 'cron list --all | grep -qi onboarding-resume' did NOT detect a disabled job -- guard is blind"
fi

# The PRE-FIX command form (bare cron list, no --all). This must NOT detect the
# disabled job with this stub -- that blindness is the exact bug being fixed.
if PATH="$STUB_PATH" bash -c 'openclaw cron list 2>/dev/null | grep -qi "onboarding-resume"'; then
  fail "1b: bare 'cron list | grep -qi onboarding-resume' unexpectedly detected the disabled job (stub is wrong)"
else
  pass "1b: bare 'cron list | grep -qi onboarding-resume' does NOT detect the disabled job (confirms the pre-fix blindness this test guards against)"
fi

# ---------------------------------------------------------------------------
# (2) HAS_ALL_FLAG: literal `cron list --all` present in the source file
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) HAS_ALL_FLAG: lib-onboarding-resume-cron.sh contains 'cron list --all' ---"

if grep -qF 'cron list --all' "$RESUME_CRON_LIB"; then
  pass "2: 'cron list --all' literal string present in lib-onboarding-resume-cron.sh"
else
  fail "2: 'cron list --all' literal string NOT found in lib-onboarding-resume-cron.sh"
fi

# ---------------------------------------------------------------------------
# (3) FAIL_CLOSED: the specific idempotency-guard line (the one that greps for
#     "onboarding-resume") must carry --all. This fails if the fix is reverted
#     back to bare `cron list`, even if `--all` still appears elsewhere in the
#     file (e.g. only in a comment).
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) FAIL_CLOSED: idempotency-guard line itself uses --all ---"

guard_line="$(grep -n 'cron list' "$RESUME_CRON_LIB" | grep 'grep -qi "onboarding-resume"' || true)"

if [[ -z "$guard_line" ]]; then
  fail "3a: could not find the idempotency-guard line (cron list ... | grep -qi \"onboarding-resume\") in lib-onboarding-resume-cron.sh -- guard missing or renamed?"
else
  guard_count="$(printf '%s\n' "$guard_line" | wc -l | tr -d ' ')"
  if [[ "$guard_count" -ne 1 ]]; then
    fail "3a: expected exactly 1 idempotency-guard line, found $guard_count -- ambiguous match"
  else
    pass "3a: found exactly 1 idempotency-guard line"
  fi

  if printf '%s\n' "$guard_line" | grep -qF -- '--all'; then
    pass "3b: idempotency-guard line uses --all (guard sees disabled jobs)"
  else
    fail "3b: idempotency-guard line does NOT use --all -- this is the exact regression: cron list hides disabled jobs, so a disabled cron is silently re-created ENABLED"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [[ "$FAIL" -gt 0 ]]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi

echo "PASS: all onboarding-resume-guard-sees-disabled checks pass"
exit 0
