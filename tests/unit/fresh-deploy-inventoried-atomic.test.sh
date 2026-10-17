#!/usr/bin/env bash
# tests/unit/fresh-deploy-inventoried-atomic.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for hardening-plan ITEM 02 — "Fresh install uses inventoried
# atomic deployment".
#
# Bug: the fresh path ran a bare `npm run build` and treated a fresh
# .next/BUILD_ID mtime as deploy proof. cc-start.sh's content gate (PRES-046)
# demands .next/build-inventory.json, which a bare build never writes — so a
# fresh box finished "built" and then refused its own child with exit 78.
#
# Required behavior:
#   * fresh deploy goes through CC's scripts/atomic-deploy.sh (private candidate
#     build, frozen-source proof, immutable manifest written by
#     scripts/lib/build-inventory.sh, atomic promotion, health check, rollback),
#     same port (--port DASHBOARD_PORT), Node resolved by atomic itself;
#   * NO legacy `npm run build` fallback — a checkout that cannot be deployed
#     that way fails loudly instead;
#   * commandCenterBuildFresh is stamped ONLY from content verification
#     (build-inventory --verify), never from a BUILD_ID timestamp;
#   * a rollback exit is reported as a degraded OLD build, never a success.
#
# Executes the REAL cc_fresh_deploy_atomic / _cc_resolve_bash4 extracted from
# run-full-install.sh against a fake atomic-deploy.sh, plus static assertions
# on the shipping installer. Fully offline/hermetic (mktemp sandbox).
# Exit 0 = all pass, 1 = failure. bash 3.2-safe: no assoc arrays, no mapfile.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== fresh-deploy-inventoried-atomic.test.sh (item 02) ==="

[ -f "$RFI" ] || { echo "  FAIL: required file not found: $RFI"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 not on PATH"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── Extract the REAL fresh-deploy function (and its bash-4 resolver) ─────────
EXTRACT_RC=0
EXTRACTED="$(python3 - "$RFI" <<'INNERPY'
import re, sys
s = open(sys.argv[1]).read()
def fn(name):
    i = s.find(name + "() {")
    if i < 0:
        sys.stderr.write("could not find %s in run-full-install.sh\n" % name)
        sys.exit(3)
    m = re.search(r"^\}$", s[i:], re.M)
    if m is None:
        sys.stderr.write("could not find the closing } of %s\n" % name)
        sys.exit(3)
    return s[i:i + m.end()]
out = fn("_cc_resolve_bash4") + "\n\n" + fn("cc_fresh_deploy_atomic")
for need in ("_cc_resolve_bash4", "cc_fresh_deploy_atomic"):
    if need + "() {" not in out:
        sys.stderr.write("extracted block missing %s\n" % need)
        sys.exit(3)
sys.stdout.write(out)
INNERPY
)" || EXTRACT_RC=$?

if [ "$EXTRACT_RC" -ne 0 ] || [ -z "$EXTRACTED" ]; then
  fail "could not extract cc_fresh_deploy_atomic from run-full-install.sh (structure changed?)"
  echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1
fi
pass "extracted the live cc_fresh_deploy_atomic + _cc_resolve_bash4 from run-full-install.sh"

# The fresh path must not carry its own legacy build. Strip comments AND quoted
# string contents first: both the doc comment and the ERROR log deliberately
# NAME the forbidden command while forbidding it. Only an actual invocation
# (which cannot survive as a bare token once strings are emptied) counts.
CODE_ONLY="$(printf '%s\n' "$EXTRACTED" \
  | sed -e 's/^[[:space:]]*#.*$//' \
  | python3 -c 'import re,sys
for line in sys.stdin:
    sys.stdout.write(re.sub(r"\"[^\"]*\"", "\"\"", line))' \
  | grep -v '^[[:space:]]*$')"
case "$CODE_ONLY" in
  *"npm run build"*) fail "cc_fresh_deploy_atomic INVOKES a bare 'npm run build' — item 02 forbids the un-inventoriable fallback" ;;
  *) pass "cc_fresh_deploy_atomic never invokes 'npm run build' (only names it in comments/log text)" ;;
esac

# ── Harness ──────────────────────────────────────────────────────────────────
DASHBOARD_DIR="$WORK/cc-checkout"
mkdir -p "$DASHBOARD_DIR" "$WORK/bin"
DASHBOARD_PORT=4000
CC_PM2_NAME="blackceo-command-center"
LOG_FILE="$WORK/install.log"
: > "$LOG_FILE"

log() { printf '%s: %s\n' "$1" "$2" >> "$LOG_FILE"; }
cc_reconcile_pm2_names() { return 0; }   # pm2 fixture churn is not this test's subject
fail_install() { printf 'FAIL_INSTALL: %s\n' "$1" >> "$LOG_FILE"; return 99; }

printf '%s\n' "$EXTRACTED" > "$WORK/fn.sh"
# shellcheck disable=SC1090
. "$WORK/fn.sh" || { fail "extracted functions failed to source"; echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1; }

# Fake atomic-deploy.sh: records argv, exits with STUB_AD_RC.
# It lives at $DASHBOARD_DIR/scripts/atomic-deploy.sh, the path the real
# helper looks for.
mkdir -p "$DASHBOARD_DIR/scripts"
cat > "$DASHBOARD_DIR/scripts/atomic-deploy.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$STUB_ARGS_FILE"
printf 'RAN\n' >> "$STUB_ARGS_FILE"
exit "${STUB_AD_RC:-0}"
STUB
chmod +x "$DASHBOARD_DIR/scripts/atomic-deploy.sh"
export STUB_ARGS_FILE="$WORK/atomic.args"

# A npm on PATH that records any invocation: proves no legacy build runs.
cat > "$WORK/bin/npm" <<'STUB'
#!/usr/bin/env bash
printf 'npm %s\n' "$*" >> "$WORK/npm.calls"
exit 0
STUB
chmod +x "$WORK/bin/npm"
export PATH="$WORK/bin:$PATH"
: > "$WORK/npm.calls"

run_case() { # run_case <atomic_rc> -> prints the helper's rc
  export STUB_AD_RC="$1"
  : > "$WORK/npm.calls"
  ( cc_fresh_deploy_atomic ) >/dev/null 2>&1
  echo $?
}

# ── A. atomic-deploy present, GREEN (rc 0) -> success, exact argv ────────────
rc="$(run_case 0)"
[ "$rc" = "0" ] && pass "atomic-deploy GREEN (rc 0) -> helper succeeds" \
  || fail "atomic-deploy rc 0 -> helper rc $rc (expected 0)"
args="$(cat "$STUB_ARGS_FILE" 2>/dev/null || true)"
expected="--app-dir $DASHBOARD_DIR --pm2-app $CC_PM2_NAME --port $DASHBOARD_PORT"
[ "$args" = "RAN" ] || [ "${args#RAN}" != "$args" ] || true
case "$args" in
  *"--app-dir $DASHBOARD_DIR"*"--pm2-app $CC_PM2_NAME"*"--port $DASHBOARD_PORT"*)
    pass "argv pins --app-dir, --pm2-app AND --port $DASHBOARD_PORT (same port as the installer)" ;;
  *) fail "unexpected atomic-deploy argv: '$args'" ;;
esac
[ -s "$WORK/npm.calls" ] && fail "GREEN path still invoked npm directly" \
  || pass "GREEN path never invokes npm itself"

# ── B. every failure exit fails loudly and is never a success ────────────────
rc="$(run_case 1)"
[ "$rc" = "1" ] && pass "rollback (rc 1) -> helper fails (degraded OLD build, not success)" \
  || fail "rollback rc 1 -> helper rc $rc (expected 1)"
grep -q "rolled back" "$LOG_FILE" && grep -q "degraded old build" "$LOG_FILE" \
  && pass "rollback is reported as a degraded old build, explicitly not a fresh deployment" \
  || fail "rollback wording missing from the log"

rc="$(run_case 2)"
[ "$rc" = "1" ] && pass "pre-flight/manifest failure (rc 2) -> helper fails" \
  || fail "rc 2 -> helper rc $rc (expected 1)"
grep -q "pre-flight/build/manifest failure" "$LOG_FILE" \
  && pass "rc 2 classified as pre-flight/build/manifest failure (candidate discarded)" \
  || fail "rc 2 classification missing"

rc="$(run_case 3)"
[ "$rc" = "1" ] && pass "health-indecisive (rc 3) -> helper fails, not success" \
  || fail "rc 3 -> helper rc $rc (expected 1)"
grep -q "INDETERMINATE" "$LOG_FILE" && grep -q "not a success" "$LOG_FILE" \
  && pass "rc 3 reported as health-indeterminate, explicitly not a success" \
  || fail "rc 3 classification missing"

rc="$(run_case 7)"
[ "$rc" = "1" ] && pass "unexpected exit 7 -> helper fails" || fail "rc 7 -> helper rc $rc (expected 1)"
grep -q "unexpected exit 7" "$LOG_FILE" && pass "unexpected exit surfaces its code" \
  || fail "unexpected exit code not surfaced"

# ── C. missing atomic-deploy.sh: loud refusal, no legacy build ────────────────
mv "$DASHBOARD_DIR/scripts/atomic-deploy.sh" "$WORK/atomic.hidden"
rc="$(run_case 0)"
[ "$rc" = "1" ] && pass "missing atomic-deploy.sh -> helper fails (rc 1)" \
  || fail "missing atomic-deploy.sh -> rc $rc (expected 1)"
grep -q "cannot be inventoried-atomically deployed" "$LOG_FILE" \
  && pass "missing atomic-deploy.sh names why the legacy build is forbidden" \
  || fail "missing atomic-deploy.sh message absent"
grep -q "exit 78 on first boot" "$LOG_FILE" \
  && pass "refusal explains the PRES-046 exit-78 consequence" \
  || fail "PRES-046 consequence not explained"
[ -s "$WORK/npm.calls" ] && fail "missing atomic-deploy.sh fell back to a bare npm build" \
  || pass "missing atomic-deploy.sh never falls back to npm run build"
mv "$WORK/atomic.hidden" "$DASHBOARD_DIR/scripts/atomic-deploy.sh"

# ── Static wiring on the shipping installer ──────────────────────────────────
# 1) The fresh branch calls the atomic helper and fail_installs otherwise.
python3 - "$RFI" <<'INNERPY' && pass "fresh branch routes through cc_fresh_deploy_atomic and fail_installs on failure" \
  || fail "fresh branch no longer routes through cc_fresh_deploy_atomic"
import sys
s = open(sys.argv[1]).read()
i = s.find("if ! cc_fresh_deploy_atomic; then")
sys.exit(0 if i > 0 and "fail_install \"phase=6: inventoried atomic deployment failed" in s[i:i+700] else 1)
INNERPY

# 2) cc_ensure_fresh_build no longer stamps BuildFresh from a timestamp.
if python3 - "$RFI" <<'INNERPY'
import re, sys
s = open(sys.argv[1]).read()
i = s.find("cc_ensure_fresh_build() {")
m = re.search(r"^\}$", s[i:], re.M)
body = s[i:i + m.end()]
# A comment may SAY the key is no longer stamped here; an actual state_set may not.
for line in body.splitlines():
    if "state_set" in line and "commandCenterBuildFresh" in line:
        sys.exit(1)
sys.exit(0)
INNERPY
then
  pass "cc_ensure_fresh_build no longer stamps commandCenterBuildFresh (timestamp is not proof)"
else
  fail "cc_ensure_fresh_build still stamps commandCenterBuildFresh from mtime"
fi

# 3) Its remaining call is the tier-3 legacy fallback only (count == 1).
n="$(grep -c 'cc_ensure_fresh_build; local _bfrc=\$?' "$RFI" || true)"
[ "$n" = "1" ] && pass "the legacy build helper is called only from tier 3 (count=$n)" \
  || fail "cc_ensure_fresh_build call count is $n (expected 1 = tier 3 only)"

# 4) The update verdicts require content verification, not only a fresh mtime.
mcount="$(grep -c 'cc_served_build_current && \[\[' "$RFI" || true)"
[ "$mcount" -ge 2 ] && pass "both update-path verdicts (tier 3 + final) require content verification ($mcount)" \
  || fail "update-path verdicts missing content gate (found $mcount, expected >= 2)"

# 5) The content oracle stamps the key in the router and the skip branch.
grep -q 'content verification PASSED' "$RFI" \
  && grep -q 'content verification FAILED' "$RFI" \
  && pass "router stamps commandCenterBuildFresh from the content oracle, both ways" \
  || fail "router no longer stamps commandCenterBuildFresh from content verification"
grep -q 'already-done box does not verify its served content' "$RFI" \
  && pass "already-done skip re-proves content validity (was never stamped there)" \
  || fail "already-done skip no longer re-proves content validity"

# 6) The startup gate itself must remain: cc-start refuses a missing manifest.
CC_START="$REPO_ROOT/../blackceo-command-center/scripts/cc-start.sh"
if [ -f "$CC_START" ]; then
  grep -q 'build-manifest-missing' "$CC_START" && grep -q 'exit 78' "$CC_START" \
    && pass "cc-start.sh PRES-046 refusal (missing manifest -> exit 78) is intact" \
    || fail "cc-start.sh content refusal changed"
else
  pass "cc-start.sh not checked out beside this repo (blackceo-command-center absent) — CC-side refusal covered by its own pres046 suites"
fi

echo ""
echo "  RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
