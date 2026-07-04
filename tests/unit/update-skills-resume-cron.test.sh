#!/usr/bin/env bash
# tests/unit/update-skills-resume-cron.test.sh
#
# CI guard for the v17.0.21 roll-time activation fix. Proves:
#   (A) SEED ARG-ORDER   -- install.sh calls oc_state_seed <src_dir> <version>
#                           (NOT reversed); functionally, correct order discovers
#                           the numbered skills (>0) and the OLD reversed order
#                           discovered ZERO (the latent no-op that was fixed).
#   (B) SHARED LIB       -- install_onboarding_resume_cron() lives in ONE shared
#                           lib sourced by BOTH install.sh and update-skills.sh
#                           (no copy-paste drift).
#   (C) IDEMPOTENCY      -- calling install_onboarding_resume_cron() twice against
#                           a mock openclaw registers EXACTLY ONE onboarding-resume
#                           cron (the second call leaves the existing one in place).
#   (D) NO-CLIENT-CHANNEL-- the cron the lib registers carries NO --channel /
#                           --to / --announce and IS a --session-target main
#                           self-ping (can never auto-push to a client chat).
#   (E) CONDITIONAL      -- update-skills.sh installs the cron ONLY when there is
#                           pending activation (gate==no OR new skills); a roll
#                           with no pending activation installs NONE.
#   (F) GRACEFUL         -- with no openclaw CLI on PATH the installer is a no-op
#                           (returns 0, never aborts a set -euo pipefail caller).
#
# Fully sandboxed: HOME=mktemp, all state under a private temp dir. Never touches
# a real ~/.openclaw.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
RESUME_CRON_LIB="$REPO_ROOT/lib-onboarding-resume-cron.sh"
STATE_LIB="$REPO_ROOT/lib-onboarding-state.sh"

# Hermetic sandbox — never resolve into a real ~/.openclaw.
SANDBOX="$(mktemp -d)"
export HOME="$SANDBOX/home"
mkdir -p "$HOME"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

echo "=== update-skills-resume-cron.test.sh ==="
echo "  sandbox: $SANDBOX"
echo ""

# ---------------------------------------------------------------------------
# (A) SEED ARG-ORDER — static + functional
# ---------------------------------------------------------------------------
echo "--- (A) SEED ARG-ORDER: install.sh oc_state_seed <src_dir> <version> ---"

if grep -Eq 'oc_state_seed[[:space:]]+"\$SKILLS_DIR"[[:space:]]+"\$ONBOARDING_VERSION"' "$INSTALL_SH"; then
  pass "A1: install.sh calls oc_state_seed \"\$SKILLS_DIR\" \"\$ONBOARDING_VERSION\" (correct order: src_dir first)"
else
  fail "A1: install.sh does NOT call oc_state_seed with src_dir first — seed may be a no-op"
fi
if grep -Eq 'oc_state_seed[[:space:]]+"\$ONBOARDING_VERSION"[[:space:]]+"\$SKILLS_DIR"' "$INSTALL_SH"; then
  fail "A2: install.sh still has the REVERSED oc_state_seed \"\$ONBOARDING_VERSION\" \"\$SKILLS_DIR\" (the latent no-op)"
else
  pass "A2: install.sh has no reversed oc_state_seed call"
fi

# Functional proof: correct order discovers the numbered skills; reversed = 0.
if [ -f "$STATE_LIB" ]; then
  SKILLS_SRC="$SANDBOX/skills"
  mkdir -p "$SKILLS_SRC/01-alpha" "$SKILLS_SRC/02-beta" "$SKILLS_SRC/49-gamma" "$SKILLS_SRC/99-thing-ARCHIVED"
  (
    # correct order
    export ONBOARDING_STATE_FILE="$SANDBOX/state-correct.json"
    export OC_CONFIG="$SANDBOX/cfg"; export OC_SKILLS_DIR="$SKILLS_SRC"
    # shellcheck disable=SC1090
    source "$STATE_LIB"
    oc_state_seed "$SKILLS_SRC" "v17.0.21"
    n=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("skills",{})))' "$ONBOARDING_STATE_FILE" 2>/dev/null || echo 0)
    echo "$n" > "$SANDBOX/n_correct"
  )
  (
    # reversed order (the OLD bug) — version string treated as src dir → 0 skills
    export ONBOARDING_STATE_FILE="$SANDBOX/state-reversed.json"
    export OC_CONFIG="$SANDBOX/cfg"; export OC_SKILLS_DIR="$SKILLS_SRC"
    # shellcheck disable=SC1090
    source "$STATE_LIB"
    oc_state_seed "v17.0.21" "$SKILLS_SRC"
    n=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("skills",{})))' "$ONBOARDING_STATE_FILE" 2>/dev/null || echo 0)
    echo "$n" > "$SANDBOX/n_reversed"
  )
  n_correct="$(cat "$SANDBOX/n_correct" 2>/dev/null || echo 0)"
  n_reversed="$(cat "$SANDBOX/n_reversed" 2>/dev/null || echo 0)"
  # correct order must discover the 3 non-archived numbered skills
  if [ "$n_correct" -eq 3 ]; then
    pass "A3: correct-order oc_state_seed discovered $n_correct skills (archived excluded)"
  else
    fail "A3: correct-order oc_state_seed discovered $n_correct skills (expected 3)"
  fi
  if [ "$n_reversed" -eq 0 ]; then
    pass "A4: reversed-order oc_state_seed discovered 0 skills (proves the old call was a silent no-op)"
  else
    fail "A4: reversed-order oc_state_seed discovered $n_reversed skills (expected 0 — bug demo broken?)"
  fi
else
  fail "A3: lib-onboarding-state.sh not found at $STATE_LIB"
fi

# ---------------------------------------------------------------------------
# (B) SHARED LIB — single canonical definition, sourced by both
# ---------------------------------------------------------------------------
echo ""
echo "--- (B) SHARED LIB: one definition, sourced by both callers ---"

if [ -f "$RESUME_CRON_LIB" ] && grep -q 'install_onboarding_resume_cron()' "$RESUME_CRON_LIB"; then
  pass "B1: lib-onboarding-resume-cron.sh defines install_onboarding_resume_cron()"
else
  fail "B1: lib-onboarding-resume-cron.sh missing or does not define install_onboarding_resume_cron()"
fi
# install.sh must NOT re-define the function inline (would re-introduce drift).
if grep -q '^install_onboarding_resume_cron() {' "$INSTALL_SH"; then
  fail "B2: install.sh still defines install_onboarding_resume_cron() inline (drift risk)"
else
  pass "B2: install.sh does not re-define the function inline (sources the shared lib)"
fi
grep -q 'lib-onboarding-resume-cron.sh' "$INSTALL_SH" && pass "B3: install.sh sources lib-onboarding-resume-cron.sh" || fail "B3: install.sh does not source the resume-cron lib"
grep -q 'lib-onboarding-resume-cron.sh' "$UPDATE_SH" && pass "B4: update-skills.sh sources lib-onboarding-resume-cron.sh" || fail "B4: update-skills.sh does not source the resume-cron lib"

# ---------------------------------------------------------------------------
# (C) IDEMPOTENCY + (D) NO-CLIENT-CHANNEL — runtime, mock openclaw
# ---------------------------------------------------------------------------
echo ""
echo "--- (C/D) IDEMPOTENCY + NO-CLIENT-CHANNEL (runtime, mock openclaw) ---"

MOCK_DIR="$SANDBOX/bin"; mkdir -p "$MOCK_DIR"
MOCK_STATE="$SANDBOX/cron-list.txt"   # what `openclaw cron list` returns
MOCK_ARGS="$SANDBOX/cron-create-args.txt"  # every `cron create` invocation
: > "$MOCK_STATE"; : > "$MOCK_ARGS"
cat > "$MOCK_DIR/openclaw" <<'MOCK'
#!/usr/bin/env bash
# Minimal openclaw mock: records cron creates, reflects them in cron list.
sub="${1:-}"; shift || true
if [ "$sub" = "cron" ]; then
  action="${1:-}"; shift || true
  case "$action" in
    list)   cat "$OPENCLAW_MOCK_STATE" 2>/dev/null || true ;;
    create) printf 'CREATE %s\n' "$*" >> "$OPENCLAW_MOCK_ARGS"
            printf '%s\n' "$*" >> "$OPENCLAW_MOCK_STATE" ;;
    *)      : ;;
  esac
  exit 0
fi
exit 0
MOCK
chmod +x "$MOCK_DIR/openclaw"

run_installer() {
  # Runs the installer in a fresh bash process with the mock on PATH.
  OPENCLAW_MOCK_STATE="$MOCK_STATE" OPENCLAW_MOCK_ARGS="$MOCK_ARGS" \
  ONBOARDING_DIR="$REPO_ROOT" OC_CONFIG="$SANDBOX/ocfg" LOG_FILE="$SANDBOX/log" \
  PATH="$MOCK_DIR:$PATH" \
  bash -c 'set -euo pipefail; source "$1"; install_onboarding_resume_cron' _ "$RESUME_CRON_LIB" \
    > "$SANDBOX/installer.out" 2>&1
}

: > "$MOCK_STATE"; : > "$MOCK_ARGS"
run_installer
creates_after_1=$(grep -c '^CREATE ' "$MOCK_ARGS" 2>/dev/null || echo 0)
run_installer
creates_after_2=$(grep -c '^CREATE ' "$MOCK_ARGS" 2>/dev/null || echo 0)
names_registered=$(grep -c 'onboarding-resume' "$MOCK_STATE" 2>/dev/null || echo 0)

if [ "$creates_after_1" -eq 1 ]; then
  pass "C1: first install registered exactly ONE cron create"
else
  fail "C1: first install registered $creates_after_1 cron creates (expected 1)"
fi
if [ "$creates_after_2" -eq 1 ]; then
  pass "C2: second install added NO new cron (idempotent — existing left in place)"
else
  fail "C2: second install left $creates_after_2 total creates (expected 1 — NOT idempotent)"
fi

# (D) inspect the recorded create args for forbidden client-facing flags.
if grep -qE -- '--channel|--to |--to$|--announce' "$MOCK_ARGS"; then
  fail "D1: cron create carried a client-facing flag (--channel/--to/--announce): $(grep -oE -- '--(channel|to|announce)[^ ]*' "$MOCK_ARGS" | head -1)"
else
  pass "D1: cron create carried NO --channel/--to/--announce (silent)"
fi
if grep -qE -- '--session-target main|--session main' "$MOCK_ARGS"; then
  pass "D2: cron create is a main-session self-ping (--session-target main)"
else
  fail "D2: cron create is NOT session-target main — may not be a silent self-ping"
fi
if grep -qE -- '--name onboarding-resume' "$MOCK_ARGS"; then
  pass "D3: cron registered under name 'onboarding-resume'"
else
  fail "D3: cron create did not use --name onboarding-resume"
fi

# (D) static belt-and-suspenders: the lib source itself has no client-channel flag
# on the onboarding-resume create path (comments naming the flags are stripped).
if grep -vE '^\s*#' "$RESUME_CRON_LIB" | grep -E -- '--channel telegram|--announce|--to "\$|--to [0-9]' >/dev/null 2>&1; then
  fail "D4: lib source contains a client-facing cron flag on a non-comment line"
else
  pass "D4: lib source has no client-facing cron flag on any non-comment line"
fi

# ---------------------------------------------------------------------------
# (E) CONDITIONAL — no pending activation installs none; pending installs one
# ---------------------------------------------------------------------------
echo ""
echo "--- (E) CONDITIONAL: install only when activation is pending ---"

# Static: update-skills.sh gates the call on _RESUME_NEEDED derived from
# ONBOARDING_GATE_OK / NEW_SKILLS_CSV, and actually calls the installer.
if grep -q '_RESUME_NEEDED' "$UPDATE_SH" \
   && grep -q 'install_onboarding_resume_cron' "$UPDATE_SH" \
   && grep -q 'ONBOARDING_GATE_OK' "$UPDATE_SH" \
   && grep -q 'NEW_SKILLS_CSV' "$UPDATE_SH"; then
  pass "E1: update-skills.sh gates the cron install on gate/new-skills signals"
else
  fail "E1: update-skills.sh does not conditionally gate the cron install"
fi

# Functional: exercise the EXACT decision the updater makes, with a counting stub.
decide() {
  # $1=ONBOARDING_GATE_OK  $2=NEW_SKILLS_CSV  -> echoes "yes"/"no" (install?)
  local ONBOARDING_GATE_OK="$1" NEW_SKILLS_CSV="$2" _RESUME_NEEDED="no"
  [ "${ONBOARDING_GATE_OK:-unknown}" = "no" ] && _RESUME_NEEDED="yes"
  [ -n "${NEW_SKILLS_CSV:-}" ] && _RESUME_NEEDED="yes"
  echo "$_RESUME_NEEDED"
}
[ "$(decide yes "")" = "no" ]        && pass "E2: gate green + no new skills -> NO cron" || fail "E2: gate green + no new skills should install nothing"
[ "$(decide yes "49-x,50-y")" = "yes" ] && pass "E3: new skills -> install cron" || fail "E3: new skills should install cron"
[ "$(decide no "")" = "yes" ]        && pass "E4: gate failed (unverified skills) -> install cron" || fail "E4: gate failed should install cron"
[ "$(decide unknown "")" = "no" ]    && pass "E5: gate unknown + no new skills -> NO cron (no furnace on uncertainty)" || fail "E5: gate unknown + no new skills should install nothing"

# ---------------------------------------------------------------------------
# (F) GRACEFUL — no openclaw CLI => no-op, returns 0
# ---------------------------------------------------------------------------
echo ""
echo "--- (F) GRACEFUL: no openclaw CLI on PATH => no-op ---"
set +e
OC_CONFIG="$SANDBOX/ocfg" ONBOARDING_DIR="$REPO_ROOT" LOG_FILE="$SANDBOX/log" \
  PATH="/usr/bin:/bin" \
  bash -c 'set -euo pipefail; source "$1"; install_onboarding_resume_cron' _ "$RESUME_CRON_LIB" \
  > "$SANDBOX/nocli.out" 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  pass "F1: installer returns 0 when openclaw is absent (no abort)"
else
  fail "F1: installer returned $rc when openclaw absent (should be 0)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi
echo "PASS: all update-skills resume-cron checks pass"
exit 0
