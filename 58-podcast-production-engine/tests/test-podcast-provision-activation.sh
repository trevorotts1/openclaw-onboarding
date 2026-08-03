#!/usr/bin/env bash
# test-podcast-provision-activation.sh - roll-1-provision verification.
#
# Tests the processor ACTIVATION wiring in 58-podcast-production-engine/scripts/
# provision-podcast-client.sh and revoke-podcast-client.sh. Fleet guarantee:
# provision => processor active; revoke => processor gone.
#
# The activation sequence (STEP 8 of provision) is GATED three ways and FAILS
# CLOSED: presence (a missing helper aborts, naming the missing piece), run rc
# (nonzero aborts), and a --check read-back (must report ACTIVE). Operator
# override --skip-activation records activation=skipped. Revocation tears the
# sequence down symmetrically (hook unregister + scheduler stop; the department
# install is box-level shared infrastructure and is NOT removed).
#
# The Workflow 1 activation helpers (register-podcast-hook.sh,
# install-podcast-department.sh, install-podcast-scheduler.sh) land in the same
# merge batch, so this test exercises the STEP 8 gate machinery against STUB
# helpers that honor the documented contract (idempotent install; "--check"
# first arg returns 0 iff the piece is active), plus structural checks on both
# scripts. It does not require a Cloudflare token or network access.
#
# Usage:
#   bash 58-podcast-production-engine/tests/test-podcast-provision-activation.sh
#
# Pass criteria (all must hold):
#   1.  bash -n provision-podcast-client.sh passes.
#   2.  bash -n revoke-podcast-client.sh passes.
#   3.  provision --help exits 0 and documents --skip-activation.
#   4.  provision accepts --skip-activation without "Unknown flag".
#   5.  activation_step: missing helper -> die 22 naming the missing piece.
#   6.  activation_step: helper present but NOT executable -> die 22.
#   7.  activation_step: helper run returns nonzero -> die (stage code).
#   8.  activation_step: helper installs but --check reports inactive -> die.
#   9.  activation_step: all three pieces install + verify ACTIVE (exact call
#       pattern: install once, then --check once, --client-slug <slug> on the
#       hook and scheduler steps).
#   10. Idempotency: re-running the sequence over already-active pieces passes.
#   11. DRY-RUN: helpers are never invoked and nothing dies.
#   12. Stage exit codes 22/23/24 are the department/hook/scheduler codes.
#   13. revoke: 5b-scheduler-stop present in BOTH the edge-only and full paths.
#   14. revoke: step 9d verifies scheduler residue (processor-gone proof).
#   15. revoke: unregisters via --remove --client-slug (symmetric to provision).
#   16. revoke: does NOT remove the shared department install.
#   17. Audit hook: provision records facts.scheduler_installer; revoke
#       resolves it from the provision ledger.
#   18. Zero em dashes in both scripts (Skill 58 convention).
#
# MUTATION PROOF (verified during development): removing the die call from the
# missing-helper branch makes test 5 FAIL (RED: the gate no longer fails closed);
# removing the post-install --check read-back makes test 8 FAIL; swapping the
# hook step's --client-slug arg for the legacy positional form makes test 9
# FAIL. Restoring the original behavior returns GREEN.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROVISION="$REPO_ROOT/58-podcast-production-engine/scripts/provision-podcast-client.sh"
REVOKE="$REPO_ROOT/58-podcast-production-engine/scripts/revoke-podcast-client.sh"

PASS_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT + 1)); echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

[ -f "$PROVISION" ] || fail "provision script missing: $PROVISION"
[ -f "$REVOKE" ] || fail "revoke script missing: $REVOKE"

# --- 1 and 2: bash -n both scripts ------------------------------------------
bash -n "$PROVISION" || fail "bash -n provision-podcast-client.sh failed"
pass "bash -n provision-podcast-client.sh passes"
bash -n "$REVOKE" || fail "bash -n revoke-podcast-client.sh failed"
pass "bash -n revoke-podcast-client.sh passes"

# --- 3 and 4: --skip-activation is parsed and documented --------------------
HELP_OUT="$(bash "$PROVISION" --help 2>&1)" || fail "provision --help exited nonzero"
printf '%s' "$HELP_OUT" | grep -q -- '--skip-activation' \
  || fail "provision --help does not document --skip-activation"
pass "provision --help exits 0 and documents --skip-activation"

HELP_OUT2="$(bash "$PROVISION" --skip-activation --help 2>&1)" || fail "--skip-activation rejected by the flag parser"
printf '%s' "$HELP_OUT2" | grep -q 'Unknown flag' \
  && fail "--skip-activation produced an Unknown flag error"
pass "provision accepts --skip-activation (no Unknown flag)"

# --- Extract the activation gate under test ----------------------------------
STATE_DIR="$(mktemp -d)"
STUB_DIR="$(mktemp -d)"
CALL_LOG="$STATE_DIR/calls"
STEPS_LOG="$STATE_DIR/steps"
FACTS_LOG="$STATE_DIR/facts"
DIE_FILE="$STATE_DIR/die"
cleanup() { rm -rf "$STATE_DIR" "$STUB_DIR" 2>/dev/null || true; }
trap cleanup EXIT

ACT_SRC="$(sed -n '/^activation_step() {/,/^}/p' "$PROVISION")"
[ -n "$ACT_SRC" ] || fail "could not extract activation_step from provision script"
TMP_LIB="$STATE_DIR/activation_step.sh"
printf '%s\n' "$ACT_SRC" > "$TMP_LIB"

# Harness stubs standing in for the script's ledger/runas/die helpers. die
# mirrors the real semantics (it exits the shell), so gate failures are run in
# subshells and the exit code plus message are captured via state files. SLUG
# is always set in production (the preflight requires it); mirror that here so
# the die messages can reference it.
DRY_RUN="0"
SLUG="tclient"
SCRIPT_DIR="$STUB_DIR"
ledger_step() { printf '[%s] %s %s\n' "$2" "$1" "${3:-}" >> "$STEPS_LOG"; }
ledger_fact() { printf '%s=%s\n' "$1" "$2" >> "$FACTS_LOG"; }
runas() { "$@"; }
die() { printf '%s\n%s\n' "$1" "$*" > "$DIE_FILE"; exit 255; }
# shellcheck source=/dev/null
source "$TMP_LIB"

reset_harness() {
  : > "$CALL_LOG"; : > "$STEPS_LOG"; : > "$FACTS_LOG"
  rm -f "$DIE_FILE"
}
run_gate() { ( activation_step "$@" ) 2>/dev/null; }
die_code() { sed -n '1p' "$DIE_FILE" 2>/dev/null || true; }
die_msg()  { sed -n '2,$p' "$DIE_FILE" 2>/dev/null | tr '\n' ' ' || true; }

# Stub helpers honoring the activation contract: log every invocation; exit 0
# unless the stub is built with a failure mode.
make_stub() {
  # make_stub <name> [run_rc] [check_rc]
  local name="$1" run_rc="${2:-0}" check_rc="${3:-0}"
  cat > "$SCRIPT_DIR/$name" <<STUB
#!/usr/bin/env bash
if [ \$# -gt 0 ]; then printf '%s %s\n' "$name" "\$*" >> "$CALL_LOG"; else printf '%s\n' "$name" >> "$CALL_LOG"; fi
if [ "\${1:-}" = "--check" ]; then exit $check_rc; fi
exit $run_rc
STUB
  chmod +x "$SCRIPT_DIR/$name"
}

# --- 5: missing helper fails closed naming the missing piece -----------------
reset_harness
rc=0; run_gate "activation:department" 22 "the podcast department installer" "install-podcast-department.sh" || rc=$?
[ "$rc" -eq 255 ] || fail "missing helper must die (subshell rc 255), got rc=$rc"
[ "$(die_code)" = "22" ] || fail "missing helper must die 22, got code=$(die_code)"
die_msg | grep -qi "department" \
  || fail "missing-helper die message must name the missing piece, got: $(die_msg)"
grep -q 'FAIL' "$STEPS_LOG" || fail "missing helper must log a FAIL step"
pass "missing helper fails closed (die 22, names the missing piece)"

# --- 6: present-but-not-executable helper fails closed ------------------------
reset_harness
printf '#!/usr/bin/env bash\nexit 0\n' > "$SCRIPT_DIR/install-podcast-department.sh"
chmod 644 "$SCRIPT_DIR/install-podcast-department.sh"
rc=0; run_gate "activation:department" 22 "the podcast department installer" "install-podcast-department.sh" || rc=$?
[ "$rc" -eq 255 ] || fail "non-executable helper must die, got rc=$rc"
[ "$(die_code)" = "22" ] || fail "non-executable helper must die 22, got code=$(die_code)"
pass "present-but-not-executable helper fails closed"
rm -f "$SCRIPT_DIR/install-podcast-department.sh"

# --- 7: helper run rc nonzero fails closed -----------------------------------
reset_harness
make_stub "install-podcast-department.sh" 1 0
rc=0; run_gate "activation:department" 22 "the podcast department installer" "install-podcast-department.sh" || rc=$?
[ "$rc" -eq 255 ] || fail "nonzero run rc must die, got rc=$rc"
[ "$(die_code)" = "22" ] || fail "nonzero run rc must die 22, got code=$(die_code)"
pass "helper run rc nonzero fails closed"
rm -f "$SCRIPT_DIR/install-podcast-department.sh"

# --- 8: installs but --check reports NOT active -> fails closed ---------------
reset_harness
make_stub "register-podcast-hook.sh" 0 1
rc=0; run_gate "activation:hook" 23 "the inbound hook registrar" "register-podcast-hook.sh" --client-slug "tclient" || rc=$?
[ "$rc" -eq 255 ] || fail "inactive --check must die, got rc=$rc"
[ "$(die_code)" = "23" ] || fail "inactive --check must die 23, got code=$(die_code)"
die_msg | grep -qi "not active" \
  || fail "inactive-read-back die message must say the piece is not active, got: $(die_msg)"
pass "install-ok-but-check-inactive fails closed"
rm -f "$SCRIPT_DIR/register-podcast-hook.sh"

# --- 9: full sequence installs + verifies ACTIVE (exact call pattern) ---------
reset_harness
make_stub "install-podcast-department.sh" 0 0
make_stub "register-podcast-hook.sh" 0 0
make_stub "install-podcast-scheduler.sh" 0 0
run_gate "activation:department" 22 "the podcast department installer" "install-podcast-department.sh" \
  || fail "healthy department step died: $(die_code) $(die_msg)"
run_gate "activation:hook" 23 "the inbound hook registrar" "register-podcast-hook.sh" --client-slug "tclient" \
  || fail "healthy hook step died: $(die_code) $(die_msg)"
run_gate "activation:scheduler" 24 "the scheduler installer" "install-podcast-scheduler.sh" --client-slug "tclient" \
  || fail "healthy scheduler step died: $(die_code) $(die_msg)"
EXPECTED_CALLS="install-podcast-department.sh
install-podcast-department.sh --check
register-podcast-hook.sh --client-slug tclient
register-podcast-hook.sh --check --client-slug tclient
install-podcast-scheduler.sh --client-slug tclient
install-podcast-scheduler.sh --check --client-slug tclient"
[ "$(cat "$CALL_LOG")" = "$EXPECTED_CALLS" ] \
  || fail "activation call pattern wrong; got: $(tr '\n' '|' < "$CALL_LOG")"
pass "full sequence: install once then --check once per piece; hook + scheduler use --client-slug"

# --- 10: idempotency - re-running over already-active pieces passes -----------
run_gate "activation:department" 22 "the podcast department installer" "install-podcast-department.sh" \
  || fail "re-run over active pieces died: $(die_code) $(die_msg)"
run_gate "activation:hook" 23 "the inbound hook registrar" "register-podcast-hook.sh" --client-slug "tclient" \
  || fail "re-run over active pieces died: $(die_code) $(die_msg)"
run_gate "activation:scheduler" 24 "the scheduler installer" "install-podcast-scheduler.sh" --client-slug "tclient" \
  || fail "re-run over active pieces died: $(die_code) $(die_msg)"
pass "idempotent: re-running activation over active pieces passes"

# --- 11: dry-run never invokes helpers and never dies --------------------------
reset_harness
rm -f "$SCRIPT_DIR/install-podcast-department.sh" "$SCRIPT_DIR/register-podcast-hook.sh" "$SCRIPT_DIR/install-podcast-scheduler.sh"
DRY_RUN="1"
run_gate "activation:department" 22 "the podcast department installer" "install-podcast-department.sh" || rc=$?
run_gate "activation:hook" 23 "the inbound hook registrar" "register-podcast-hook.sh" --client-slug "tclient" || rc=$?
run_gate "activation:scheduler" 24 "the scheduler installer" "install-podcast-scheduler.sh" --client-slug "tclient" || rc=$?
DRY_RUN="0"
[ -f "$DIE_FILE" ] && fail "dry-run must not die even with missing helpers, got: $(die_code) $(die_msg)"
[ -s "$CALL_LOG" ] && fail "dry-run must never invoke helpers"
grep -q 'DRY-RUN' "$STEPS_LOG" || fail "dry-run must log DRY-RUN steps"
pass "dry-run: helpers never invoked, nothing dies"

# --- 12: stage exit codes 22/23/24 are wired in the STEP 8 block --------------
for pair in "22:install-podcast-department.sh" "23:register-podcast-hook.sh" "24:install-podcast-scheduler.sh"; do
  code="${pair%%:*}"; helper="${pair#*:}"
  grep -E "activation_step \"activation:[a-z]+\"[[:space:]]+${code}[[:space:]].*${helper}" "$PROVISION" >/dev/null \
    || fail "STEP 8 must call activation_step with exit code $code for $helper"
done
pass "stage exit codes wired: 22 department, 23 hook, 24 scheduler"

# --- 13: revoke has 5b-scheduler-stop on BOTH paths ---------------------------
EDGE_PATH_COUNT="$(sed -n '/EDGE_ONLY" = "1" \]; then/,/^else$/p' "$REVOKE" | grep -c '5b-scheduler-stop' || true)"
FULL_PATH_COUNT="$(sed -n '/^else$/,/^fi$/p' "$REVOKE" | grep -c '5b-scheduler-stop' || true)"
[ "${EDGE_PATH_COUNT:-0}" -ge 1 ] || fail "edge-only path must record 5b-scheduler-stop PENDING"
[ "${FULL_PATH_COUNT:-0}" -ge 1 ] || fail "full path must run 5b-scheduler-stop teardown"
pass "revoke: 5b-scheduler-stop present in edge-only and full paths"

# --- 14: revoke step 9d verifies scheduler residue -----------------------------
grep -q 'scheduler STILL ACTIVE' "$REVOKE" \
  || fail "9d-box-clean must detect a still-active scheduler"
grep -q -- '--check --client-slug' "$REVOKE" \
  || fail "9d must use the scheduler installer --check read-back"
pass "revoke: step 9d verifies the scheduler is gone"

# --- 15: revoke unregisters symmetrically via --remove --client-slug -----------
grep -q -- '--remove --client-slug' "$REVOKE" \
  || fail "revoke must unregister the hook with --remove --client-slug (symmetric to provision)"
pass "revoke: hook unregister uses --remove --client-slug"

# --- 16: revoke does NOT remove the shared department install ------------------
grep -E 'install-podcast-department\.sh.*--remove' "$REVOKE" >/dev/null \
  && fail "revoke must NOT remove the box-level shared department install"
pass "revoke: shared department install is preserved"

# --- 17: audit hook - provision records the installer, revoke resolves it ------
grep -q 'ledger_fact "scheduler_installer"' "$PROVISION" \
  || fail "provision must record facts.scheduler_installer for the fleet audit"
grep -q 'scheduler_installer' "$REVOKE" \
  || fail "revoke must resolve the scheduler installer from the provision ledger fact"
pass "audit hook: provision records scheduler_installer; revoke resolves it"

# --- 18: zero em dashes (Skill 58 convention) ----------------------------------
if grep -q $'\xe2\x80\x94' "$PROVISION" "$REVOKE"; then
  fail "em dash found in provision or revoke script"
fi
pass "zero em dashes in both scripts"

echo ""
echo "ALL $PASS_COUNT TESTS PASSED"
