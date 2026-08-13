#!/usr/bin/env bash
# tests/unit/onboarding-resume-no-rearm-after-escalation.test.sh
#
# CI guard for the SECOND onboarding-resume-cron re-arm guard
# (fix/loop-fault-class-20260811). scripts/resume-onboarding.sh sets
# .onboarding-state.json's `.resumeEscalated = true` when it hits
# MAX_RUNS_BEFORE_ESCALATE and self-deletes -- the box already gave up and
# told the operator so. Until this guard, that flag was write-only (nothing
# ever read it): a later roll through install_onboarding_resume_cron() saw no
# existing cron (the prior one self-removed) and re-created it ENABLED
# anyway, re-arming the */30 self-ping into a box that had already declared
# defeat. Observed live: a box whose gate could never pass (11 skills stuck
# qc-failed) had its onboarding-resume cron re-created enabled at 21:20:14
# despite resumeEscalated already being true.
#
# Assertion groups (three branches of _onboarding_resume_already_escalated /
# install_onboarding_resume_cron, each proven functionally against a stubbed
# openclaw that records every `cron create` call):
#   (1) ESCALATED_BLOCKS   -- resumeEscalated:true  -> NO cron create attempted,
#                             a warn is emitted, function returns 0.
#   (2) NOT_ESCALATED_INSTALLS -- resumeEscalated:false (and key-absent) ->
#                             normal install path proceeds, cron create IS
#                             attempted.
#   (3) FAIL_OPEN          -- state file missing/unreadable -> normal install
#                             path proceeds (absence of evidence must never
#                             block a legitimate first-time install).
#
# Hermetic: a stub `openclaw` on PATH in a scratch temp dir records `cron
# create` invocations to a log file; the real lib-onboarding-resume-cron.sh
# and the real scripts/resume-onboarding-prompt.txt are sourced/read
# read-only. No live gateway, no real cron store, no real ~/.openclaw.
#
# Run: bash tests/unit/onboarding-resume-no-rearm-after-escalation.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more checks failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESUME_CRON_LIB="$REPO_ROOT/lib-onboarding-resume-cron.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

# count_creates FILE -- number of '^CREATE ' lines, always a single bare
# integer. `grep -c` alone would suffice (it prints "0" and exits 1 on zero
# matches), but naively falling back with `|| echo 0` on that nonzero exit
# double-prints ("0\n0") for the exact zero-match case this test needs to
# assert on -- so no `||` fallback here; the calls log always exists.
count_creates() { grep -c '^CREATE ' "$1" 2>/dev/null; }

echo "=== onboarding-resume-no-rearm-after-escalation.test.sh ==="
echo ""

if [[ ! -f "$RESUME_CRON_LIB" ]]; then
  echo "FATAL: lib-onboarding-resume-cron.sh not found at $RESUME_CRON_LIB" >&2
  exit 1
fi

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/onboarding-resume-rearm.XXXXXX")"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

mkdir -p "$SANDBOX/bin"

# Stub openclaw:
#   `cron list [--all]`      -> always empty (no pre-existing cron; first
#                                idempotency guard never short-circuits, so
#                                every branch here actually exercises the
#                                SECOND guard under test).
#   `cron add --help`        -> advertise the modern --session flag so
#                                _oc_cron_silent_main takes a single, simple path.
#   `cron create ...`        -> record the call and succeed.
cat > "$SANDBOX/bin/openclaw" <<STUBEOF
#!/usr/bin/env bash
CALLS_LOG="$SANDBOX/cron-calls.log"
if [ "\${1:-}" = "cron" ] && [ "\${2:-}" = "list" ]; then
  exit 0
fi
if [ "\${1:-}" = "cron" ] && [ "\${2:-}" = "add" ] && [ "\${3:-}" = "--help" ]; then
  echo "  --session <name>   target session (modern form)"
  exit 0
fi
if [ "\${1:-}" = "cron" ] && [ "\${2:-}" = "create" ]; then
  printf 'CREATE %s\n' "\$*" >> "\$CALLS_LOG"
  exit 0
fi
exit 0
STUBEOF
chmod +x "$SANDBOX/bin/openclaw"

# run_install STATE_MODE -> runs install_onboarding_resume_cron() in a fresh
# bash process with the stub openclaw on PATH and a state file prepared per
# STATE_MODE ("escalated" / "not-escalated" / "key-absent" / "missing" /
# "unreadable"). Echoes the function's exit code; cron-create attempts land in
# $SANDBOX/cron-calls.log (truncated before each run) and stderr/stdout are
# captured for inspection.
run_install() {
  local mode="$1"
  local calls_log="$SANDBOX/cron-calls.log"
  local state_file="$SANDBOX/state.json"
  : > "$calls_log"
  rm -f "$state_file"
  local onboarding_state_file_env="$state_file"

  case "$mode" in
    escalated)      echo '{"resumeEscalated": true}'  > "$state_file" ;;
    not-escalated)  echo '{"resumeEscalated": false}' > "$state_file" ;;
    key-absent)     echo '{"otherField": 1}'           > "$state_file" ;;
    missing)        onboarding_state_file_env="$SANDBOX/does-not-exist.json" ;;
    unreadable)
      echo '{"resumeEscalated": true}' > "$state_file"
      chmod 000 "$state_file"
      ;;
    *) echo "run_install: unknown mode '$mode'" >&2; return 99 ;;
  esac

  PATH="$SANDBOX/bin:$PATH" \
  ONBOARDING_DIR="$REPO_ROOT" \
  OC_CONFIG="$SANDBOX/ocfg-$mode" \
  ONBOARDING_STATE_FILE="$onboarding_state_file_env" \
  LOG_FILE="$SANDBOX/log" \
  bash -c 'set -euo pipefail; source "$1"; install_onboarding_resume_cron' _ "$RESUME_CRON_LIB" \
    > "$SANDBOX/out-$mode.log" 2>&1
  local rc=$?
  chmod 644 "$state_file" 2>/dev/null || true   # so cleanup can remove it
  return "$rc"
}

# ---------------------------------------------------------------------------
# (1) ESCALATED_BLOCKS -- resumeEscalated:true -> no cron create attempted
# ---------------------------------------------------------------------------
echo "--- (1) ESCALATED_BLOCKS: resumeEscalated=true -> cron creation NOT attempted ---"

run_install escalated
rc1=$?
creates1=$(count_creates "$SANDBOX/cron-calls.log")

if [ "$rc1" -eq 0 ]; then
  pass "1a: install_onboarding_resume_cron returns 0 when already escalated (never aborts caller)"
else
  fail "1a: install_onboarding_resume_cron returned $rc1 when already escalated (expected 0)"
fi
if [ "$creates1" -eq 0 ]; then
  pass "1b: NO 'cron create' was attempted when resumeEscalated=true"
else
  fail "1b: 'cron create' WAS attempted ($creates1 call(s)) despite resumeEscalated=true -- re-arm guard missing/broken"
fi
if grep -qi "escalat" "$SANDBOX/out-escalated.log"; then
  pass "1c: a warning naming the escalation was emitted"
else
  fail "1c: no escalation warning found in installer output"
fi

# ---------------------------------------------------------------------------
# (2) NOT_ESCALATED_INSTALLS -- resumeEscalated:false / key absent -> normal
#     install proceeds and cron create IS attempted
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) NOT_ESCALATED_INSTALLS: resumeEscalated=false / key-absent -> normal install proceeds ---"

run_install not-escalated
rc2=$?
creates2=$(count_creates "$SANDBOX/cron-calls.log")
if [ "$rc2" -eq 0 ] && [ "$creates2" -ge 1 ]; then
  pass "2a: resumeEscalated=false -> normal install proceeded ($creates2 cron create call(s))"
else
  fail "2a: resumeEscalated=false -> install did not proceed as expected (rc=$rc2, creates=$creates2)"
fi
if grep -qE -- '--name onboarding-resume' "$SANDBOX/cron-calls.log"; then
  pass "2b: the cron create call registered under name 'onboarding-resume'"
else
  fail "2b: no 'cron create --name onboarding-resume' call recorded"
fi

run_install key-absent
rc2b=$?
creates2b=$(count_creates "$SANDBOX/cron-calls.log")
if [ "$rc2b" -eq 0 ] && [ "$creates2b" -ge 1 ]; then
  pass "2c: resumeEscalated key ABSENT -> normal install proceeded ($creates2b cron create call(s))"
else
  fail "2c: resumeEscalated key absent -> install did not proceed as expected (rc=$rc2b, creates=$creates2b)"
fi

# ---------------------------------------------------------------------------
# (3) FAIL_OPEN -- state file missing/unreadable -> normal install proceeds
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) FAIL_OPEN: state file missing/unreadable -> normal install proceeds ---"

run_install missing
rc3=$?
creates3=$(count_creates "$SANDBOX/cron-calls.log")
if [ "$rc3" -eq 0 ] && [ "$creates3" -ge 1 ]; then
  pass "3a: MISSING state file -> fail-open, normal install proceeded ($creates3 cron create call(s))"
else
  fail "3a: MISSING state file -> install did not proceed (rc=$rc3, creates=$creates3) -- guard is blocking on absence of evidence"
fi

if [ "$(id -u)" -eq 0 ]; then
  echo "  SKIP: 3b (unreadable-file case) -- running as root, chmod 000 does not deny root reads"
  pass "3b: skipped under root (chmod 000 is not enforced for uid 0)"
else
  run_install unreadable
  rc3b=$?
  creates3b=$(count_creates "$SANDBOX/cron-calls.log")
  if [ "$rc3b" -eq 0 ] && [ "$creates3b" -ge 1 ]; then
    pass "3b: UNREADABLE state file -> fail-open, normal install proceeded ($creates3b cron create call(s))"
  else
    fail "3b: UNREADABLE state file -> install did not proceed (rc=$rc3b, creates=$creates3b) -- guard is blocking on unreadable evidence"
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

echo "PASS: all onboarding-resume-no-rearm-after-escalation checks pass"
exit 0
