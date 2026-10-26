#!/usr/bin/env bash
# tests/unit/cron-presence-unknown-d10.test.sh
#
# D10: cron presence checks treated a FAILED or NON-JSON `openclaw cron list` as
# "job absent", so every registrar added a duplicate whenever the gateway was
# slow or restarting (ghl-mcp-probe x4, closeout-readiness-watchdog x3, ...).
# Contract now: oc_cron_present / _cron_present return 0 = present, 1 = absent
# (a good list without the job), 2 = UNKNOWN (CLI failed / unparseable). A
# registrar adds ONLY on a definite "absent".
#
# Hermetic: private $HOME, sandboxed copies, fake `openclaw` (tests/fixtures/
# fake-openclaw-cron.py with $FAKE_OC_LIST_MODE failure injection).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox inside a real .openclaw"; exit 2 ;; esac

echo "=== cron-presence-unknown-d10.test.sh ==="

BIN="$SANDBOX/bin"; mkdir -p "$BIN"
printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$BIN/openclaw"; chmod +x "$BIN/openclaw"

SK="$SANDBOX/repo"; mkdir -p "$SK/shared-utils" "$SK/scripts"
cp -r "$REPO_ROOT/38-conversational-ai-system" "$REPO_ROOT/39-real-estate-playbook" "$REPO_ROOT/31-upgraded-memory-system" "$SK/"
cp "$REPO_ROOT/shared-utils/"*.sh "$SK/shared-utils/"
cp "$REPO_ROOT/scripts/ensure-pipeline-crons.sh" "$SK/scripts/"
mkdir -p "$SK/06-ghl-install-pages/scripts"
cp "$REPO_ROOT/06-ghl-install-pages/scripts/install-routing-drift-check-cron.sh" "$SK/06-ghl-install-pages/scripts/"
# The installer's idempotency guard now lives in this shared helper (full
# visibility via --all + tri-state presence); copy it beside the installer.
cp "$REPO_ROOT/06-ghl-install-pages/scripts/lib-cron-presence.sh" "$SK/06-ghl-install-pages/scripts/"
cp -r "$REPO_ROOT/06-ghl-install-pages/schedule" "$SK/06-ghl-install-pages/"

HOME_D="$SANDBOX/home"; mkdir -p "$HOME_D/.openclaw/workspace"
export MASTER_FILES_DIR="$SANDBOX/master-files"; mkdir -p "$MASTER_FILES_DIR"
printf '%s' '{"industryPack":{"slug":"real-estate","source":"owner-confirmed"}}' > "$HOME_D/.openclaw/workspace/.workforce-build-state.json"

# run <mode> <jobs-json> <logfile> <cmd...> ; jobs-json "" = no file
run() {
  local mode="$1" jobs="$2" calls="$3"; shift 3
  printf '%s' "$jobs" > "$SANDBOX/jobs.json"; : > "$calls"
  HOME="$HOME_D" PATH="$BIN:$PATH" FAKE_OC_LIST_MODE="$mode" FAKE_OC_JOBS_FILE="$SANDBOX/jobs.json" \
    FAKE_OC_CALLS_FILE="$calls" "$@" >"$SANDBOX/out.log" 2>&1
}
adds() { grep -E '^cron (add|create) ' "$1" 2>/dev/null | grep -vc -- '--help' || true; }

# ---- 1. oc_cron_present tri-state (shared-utils/cron-lib.sh) -----------------
echo "--- oc_cron_present return codes ---"
probe() { # <mode> <jobs> -> prints rc
  printf '%s' "$2" > "$SANDBOX/jobs.json"
  HOME="$HOME_D" PATH="$BIN:$PATH" FAKE_OC_LIST_MODE="$1" FAKE_OC_JOBS_FILE="$SANDBOX/jobs.json" \
    bash -c 'source "'"$SK"'/shared-utils/cron-lib.sh"; oc_cron_present target-job >/dev/null 2>&1; echo $?'
}
PRESENT='[{"name":"target-job","id":"x"}]'; ABSENT='[{"name":"other","id":"y"}]'
[ "$(probe fail "$PRESENT")" = 2 ]    && pass "CLI failure (rc 1) -> 2 unknown"      || fail "CLI failure did not return 2"
[ "$(probe garbage "$PRESENT")" = 2 ] && pass "non-JSON output -> 2 unknown"         || fail "non-JSON did not return 2"
[ "$(probe empty "$PRESENT")" = 2 ]   && pass "empty output -> 2 unknown"            || fail "empty output did not return 2"
[ "$(probe '' "$ABSENT")" = 1 ]       && pass "valid JSON without the job -> 1 absent"  || fail "valid list without job did not return 1"
[ "$(probe '' "$PRESENT")" = 0 ]      && pass "valid JSON with the job -> 0 present"    || fail "valid list with job did not return 0"
# python3-only path (no jq on PATH)
NOJQ="$SANDBOX/nojq"; mkdir -p "$NOJQ"
for t in bash env python3 cat grep sed head tr cut dirname mkdir printf; do p="$(command -v $t)" && ln -sf "$p" "$NOJQ/$t"; done
probe_nojq() { printf '%s' "$2" > "$SANDBOX/jobs.json"
  HOME="$HOME_D" PATH="$BIN:$NOJQ" FAKE_OC_LIST_MODE="$1" FAKE_OC_JOBS_FILE="$SANDBOX/jobs.json" \
    "$NOJQ/bash" -c 'source "'"$SK"'/shared-utils/cron-lib.sh"; oc_cron_present target-job >/dev/null 2>&1; echo $?'; }
[ "$(probe_nojq garbage "$PRESENT")" = 2 ] && [ "$(probe_nojq '' "$ABSENT")" = 1 ] && [ "$(probe_nojq '' "$PRESENT")" = 0 ] \
  && pass "python3-only path: garbage 2 / absent 1 / present 0" || fail "python3-only path wrong"

# ---- 2. registrars never add on unknown, add once on definite absent ---------
echo "--- registrars: skill 31 (cron-lib), skill 39, skill 38 ---"
for mode in fail garbage empty; do
  for reg in "31-upgraded-memory-system/install.sh" "39-real-estate-playbook/scripts/07-register-crons.sh" "38-conversational-ai-system/scripts/04-register-crons.sh"; do
    run "$mode" '[]' "$SANDBOX/calls.log" bash "$SK/$reg"
    n=$(adds "$SANDBOX/calls.log")
    [ "$n" -eq 0 ] && pass "$reg [$mode]: no cron add" || fail "$reg [$mode]: $n cron add call(s) on an unreadable list (duplicate risk)"
  done
done
run '' '[]' "$SANDBOX/calls.log" bash "$SK/31-upgraded-memory-system/install.sh"
[ "$(adds "$SANDBOX/calls.log")" -eq 2 ] && pass "skill 31 [valid empty list]: registers its 2 crons exactly once" || fail "skill 31 did not add exactly 2 crons on a valid empty list"
run '' '[{"name":"memory-index-check","id":"a","kind":"command"},{"name":"memory-cache-prune","id":"b","kind":"command"}]' "$SANDBOX/calls.log" bash "$SK/31-upgraded-memory-system/install.sh"
[ "$(adds "$SANDBOX/calls.log")" -eq 0 ] && pass "skill 31 [both present]: no add" || fail "skill 31 added a cron that was present"
run '' '[]' "$SANDBOX/calls.log" bash "$SK/39-real-estate-playbook/scripts/07-register-crons.sh"
[ "$(adds "$SANDBOX/calls.log")" -ge 1 ] && pass "skill 39 [valid empty list]: still registers" || fail "skill 39 registered nothing on a valid empty list"

# ---- 3. skill 06 installer (own _cron_present) --------------------------------
echo "--- skill 06 installer ---"
INST="$SK/06-ghl-install-pages/scripts/install-routing-drift-check-cron.sh"
for mode in fail garbage; do
  run "$mode" '[]' "$SANDBOX/calls.log" bash "$INST"
  [ "$(adds "$SANDBOX/calls.log")" -eq 0 ] && pass "install-routing-drift-check-cron [$mode]: no cron add" || fail "install-routing-drift-check-cron [$mode]: added on unreadable list"
done
run '' '[]' "$SANDBOX/calls.log" bash "$INST"
[ "$(adds "$SANDBOX/calls.log")" -eq 1 ] && pass "install-routing-drift-check-cron [valid empty list]: one add" || fail "install-routing-drift-check-cron [valid empty list]: expected one add"

# ---- 4. scripts/ensure-pipeline-crons.sh --------------------------------------
echo "--- scripts/ensure-pipeline-crons.sh ---"
ENS="$SK/scripts/ensure-pipeline-crons.sh"
# a health script on the persistent scripts path so _ensure_health_cron gets past its SKIP
mkdir -p "$HOME_D/.openclaw/scripts"; printf '#!/bin/sh\nexit 0\n' > "$HOME_D/.openclaw/scripts/index-model-drift-check.sh"
for mode in fail garbage; do
  run "$mode" '[]' "$SANDBOX/calls.log" bash "$ENS"
  n=$(adds "$SANDBOX/calls.log")
  [ "$n" -eq 0 ] && pass "ensure-pipeline-crons [$mode]: no cron add" || fail "ensure-pipeline-crons [$mode]: $n cron add call(s) on an unreadable list"
done
run '' '[]' "$SANDBOX/calls.log" bash "$ENS"
[ "$(adds "$SANDBOX/calls.log")" -ge 1 ] && pass "ensure-pipeline-crons [valid empty list]: registers crons" || fail "ensure-pipeline-crons registered nothing on a valid empty list"

# ---- 5. ghl-mcp-autostart cron-store fallback ---------------------------------
echo "--- scripts/ghl-mcp-autostart.sh probe registration ---"
if grep -q 'presence unknown, NOT registering' "$REPO_ROOT/scripts/ghl-mcp-autostart.sh" \
   && ! grep -q "cron list --json 2>/dev/null | grep -q '\"name\": \*\"ghl-mcp-probe\"'" "$REPO_ROOT/scripts/ghl-mcp-autostart.sh"; then
  pass "autostart skips ghl-mcp-probe registration when cron list is unreadable"
else
  fail "autostart still registers ghl-mcp-probe on a failed cron list"
fi

echo ""; echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
