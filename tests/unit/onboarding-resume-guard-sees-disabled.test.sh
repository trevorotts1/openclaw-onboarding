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
#   (4) INSTALLS_WHEN_MISSING -- against the REAL install_onboarding_resume_cron()
#                           sourced from lib-onboarding-resume-cron.sh: with a
#                           stub openclaw whose `cron list --all` shows NO
#                           onboarding-resume line, the installer PROCEEDS and
#                           makes a `cron create` attempt. (1)-(3) only prove
#                           the guard's command-form mechanics; they do not
#                           prove the function acts on the guard's answer -- a
#                           guard that always reported "already exists" would
#                           pass (1)-(3) untouched while silently preventing
#                           onboarding from EVER installing this cron on a
#                           fresh box.
#   (5) SKIPS_WHEN_PRESENT -- same real function, stub's `cron list --all`
#                           DOES show an onboarding-resume line -> the
#                           installer makes ZERO `cron create` calls (no
#                           duplicate stacked). Same both-directions
#                           discipline as
#                           tests/unit/ghl-mcp-autostart-idempotent-write.test.sh
#                           (matched-value -> no write, drifted-value -> write).
#
# Hermetic: a fake `openclaw` on PATH in a scratch temp dir, isolated HOME, and
# an isolated ONBOARDING_DIR/ONBOARDING_STATE_FILE for (4)/(5). No live
# gateway, no real cron store, no real onboarding state, is touched.
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
# (4)/(5) BOTH-DIRECTIONS INSTALLER CHECK, against the REAL
#   install_onboarding_resume_cron() sourced from lib-onboarding-resume-cron.sh
#   (not a re-implementation of its logic). See header comment for why this
#   closes a gap that (1)-(3) alone cannot catch.
# ---------------------------------------------------------------------------
echo ""
echo "--- (4)/(5) real install_onboarding_resume_cron(): both directions ---"

# run_install_case CRON_EXISTS
#   Runs the REAL install_onboarding_resume_cron(), sourced fresh from
#   lib-onboarding-resume-cron.sh, inside an isolated HOME/PATH/ONBOARDING_DIR
#   sandbox in its own subshell -- nothing here touches the real environment
#   and nothing can message anywhere. A stub `openclaw` on PATH records every
#   invocation (space-joined args, one per line) to a call-log file; echoes
#   the path to that file on stdout.
#     CRON_EXISTS=0 -> stub's `cron list --all` shows NO onboarding-resume
#                      line (fresh box, nothing installed yet).
#     CRON_EXISTS=1 -> stub's `cron list --all` DOES show an onboarding-resume
#                      line (already installed -- the guard only checks
#                      presence, so this also stands in for the disabled case
#                      proven separately in (1)).
#   The resume-prompt file and escalation-state guard are satisfied/avoided
#   per the REAL resolver functions in the lib (_resolve_resume_prompt_file,
#   _resolve_onboarding_state_file, _onboarding_resume_already_escalated),
#   not assumed:
#     - ONBOARDING_DIR points at a temp dir containing
#       scripts/resume-onboarding-prompt.txt (the first candidate
#       _resolve_resume_prompt_file checks), so the installer has a prompt to
#       proceed with.
#     - ONBOARDING_STATE_FILE points at a path that does NOT exist, and HOME
#       is isolated so none of _resolve_onboarding_state_file's other
#       candidates (including $HOME/.openclaw/workspace/...) can resolve to a
#       real file on this machine -- _onboarding_resume_already_escalated
#       therefore fails open (returns 1 / not escalated) exactly per its
#       documented "no resolvable state file" behaviour, so that guard never
#       blocks case (4).
run_install_case() {
  local cron_exists="$1"
  local case_dir
  case_dir="$(mktemp -d "$SANDBOX/install-case.XXXXXX")"
  mkdir -p "$case_dir/bin" "$case_dir/home" "$case_dir/onboarding/scripts"
  printf 'test resume prompt content\n' > "$case_dir/onboarding/scripts/resume-onboarding-prompt.txt"
  : > "$case_dir/calls.log"

  cat > "$case_dir/bin/openclaw" <<STUBEOF
#!/usr/bin/env bash
# Stub openclaw for this case only. Logs every invocation, then answers just
# enough for install_onboarding_resume_cron()'s real decision logic to run.
echo "\$@" >> "$case_dir/calls.log"
if [ "\${1:-}" = "cron" ] && [ "\${2:-}" = "list" ]; then
  shift 2
  for _a in "\$@"; do
    if [ "\$_a" = "--all" ]; then
      if [ "$cron_exists" = "1" ]; then
        echo "job-7a  onboarding-resume  enabled=true  */30 * * * *"
      fi
      exit 0
    fi
  done
  exit 0
fi
if [ "\${1:-}" = "cron" ] && [ "\${2:-}" = "add" ] && [ "\${3:-}" = "--help" ]; then
  # Deliberately not the modern --session form, so _oc_cron_silent_main takes
  # a defined (old-flag) branch instead of depending on probe-text parsing.
  echo "usage: cron add <expr> <prompt> --name NAME --agent AGENT"
  exit 0
fi
if [ "\${1:-}" = "cron" ] && [ "\${2:-}" = "create" ]; then
  exit 0
fi
exit 0
STUBEOF
  chmod +x "$case_dir/bin/openclaw"

  (
    HOME="$case_dir/home"
    PATH="$case_dir/bin:/usr/bin:/bin"
    ONBOARDING_DIR="$case_dir/onboarding"
    ONBOARDING_STATE_FILE="$case_dir/home/does-not-exist.json"
    export HOME PATH ONBOARDING_DIR ONBOARDING_STATE_FILE
    unset OC_PERSISTENT_SCRIPTS_DIR OC_CONFIG OC_WORKSPACE_DEFAULT TELEGRAM_DEFAULT_AGENT_CACHED LOG_FILE 2>/dev/null
    # shellcheck disable=SC1090
    source "$RESUME_CRON_LIB"
    install_onboarding_resume_cron
  ) >/dev/null 2>&1

  printf '%s' "$case_dir/calls.log"
}

echo ""
echo "--- (4) INSTALLS_WHEN_MISSING: no cron present -> installer attempts creation ---"

log4="$(run_install_case 0)"
create_calls4="$(grep -c '^cron create ' "$log4" 2>/dev/null || true)"
if [[ "${create_calls4:-0}" -ge 1 ]] && grep -q '^cron create .*--name onboarding-resume' "$log4" 2>/dev/null; then
  pass "4: no onboarding-resume cron present -> installer made ${create_calls4} 'cron create' attempt(s) naming onboarding-resume"
else
  fail "4: no onboarding-resume cron present but installer made NO 'cron create' attempt -- a fresh box would never get this cron installed"
fi

echo ""
echo "--- (5) SKIPS_WHEN_PRESENT: cron already present -> installer makes ZERO creation attempts ---"

log5="$(run_install_case 1)"
create_calls5="$(grep -c '^cron create ' "$log5" 2>/dev/null || true)"
if [[ "${create_calls5:-0}" -eq 0 ]]; then
  pass "5: onboarding-resume cron already present -> installer made 0 'cron create' calls (no duplicate stacked)"
else
  fail "5: onboarding-resume cron already present but installer made ${create_calls5} 'cron create' call(s) -- would stack a duplicate"
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
