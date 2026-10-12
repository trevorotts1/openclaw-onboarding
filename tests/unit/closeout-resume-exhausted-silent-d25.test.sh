#!/usr/bin/env bash
# tests/unit/closeout-resume-exhausted-silent-d25.test.sh
#
# D25: every update-skills run re-registered a closeout-resume cron on boxes whose
# closeout was already complete (or whose run budget was spent); its first fire then
# Telegrammed "Closeout resume cron exhausted" through the client's own bot.
#   (1) closeout done/sent  -> ensure-pipeline-crons + installer register nothing
#   (2) budget spent        -> register nothing
#   (3) fresh registration  -> registers once and resets a stale run counter
#   (4) exhausted job       -> removes itself, sends NO message (even with operator chat)
# Hermetic: private $HOME, fake `openclaw` (tests/fixtures/fake-openclaw-cron.py).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
[[ -d /data/.openclaw ]] && { echo "SKIP: /data/.openclaw exists on this host"; exit 0; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox inside a real .openclaw"; exit 2 ;; esac
echo "=== closeout-resume-exhausted-silent-d25.test.sh ==="

BIN="$SANDBOX/bin"; mkdir -p "$BIN"
printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$BIN/openclaw"; chmod +x "$BIN/openclaw"
SK="$SANDBOX/repo"; mkdir -p "$SK/scripts" "$SK/shared-utils"
cp -r "$REPO_ROOT/37-zhc-closeout" "$SK/"
cp -r "$REPO_ROOT/23-ai-workforce-blueprint" "$SK/"
cp "$REPO_ROOT/shared-utils/"* "$SK/shared-utils/" 2>/dev/null
cp "$REPO_ROOT/scripts/ensure-pipeline-crons.sh" "$SK/scripts/"
H="$SANDBOX/home"; WS="$H/.openclaw/workspace"; STATE="$WS/.workforce-build-state.json"; CNT="$WS/.closeout-resume-runs.count"
mkdir -p "$WS" "$H/.openclaw/skills"
cp -r "$SK/37-zhc-closeout" "$SK/23-ai-workforce-blueprint" "$SK/shared-utils" "$H/.openclaw/skills/"
export MASTER_FILES_DIR="$SANDBOX/master-files"; mkdir -p "$MASTER_FILES_DIR"

# run <state-json> <count|""> <script> ; leaves calls in $SANDBOX/calls.log
run() {
  printf '%s' "$1" > "$STATE"; rm -f "$CNT"; [[ -n "$2" ]] && printf '%s\n' "$2" > "$CNT"
  printf '[]' > "$SANDBOX/jobs.json"; : > "$SANDBOX/calls.log"
  env -i PATH="$BIN:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" HOME="$H" TMPDIR="$SANDBOX" \
    OC_ROOT="$H/.openclaw" MASTER_FILES_DIR="$MASTER_FILES_DIR" OPERATOR_ESCALATION_CHAT_ID=555000111 \
    FAKE_OC_JOBS_FILE="$SANDBOX/jobs.json" FAKE_OC_CALLS_FILE="$SANDBOX/calls.log" \
    bash "$3" >"$SANDBOX/out.log" 2>&1
}
resume_adds() { grep -E '^cron (add|create) ' "$SANDBOX/calls.log" | grep -- 'closeout-resume' | grep -vc -- '--help' || true; }
ENS="$SK/scripts/ensure-pipeline-crons.sh"
INST="$H/.openclaw/skills/37-zhc-closeout/scripts/install-closeout-resume-cron.sh"

DONE='{"buildCompletedAt":"2026-01-01T00:00:00Z","closeoutStatus":"done"}'
OPEN='{"buildCompletedAt":"2026-01-01T00:00:00Z","closeoutStatus":"pending"}'

echo "--- (1) closeout complete -> no registration ---"
for st in done sent; do
  run "${DONE/done/$st}" "" "$ENS"
  [ "$(resume_adds)" -eq 0 ] && pass "ensure-pipeline-crons [$st]: no closeout-resume add" || fail "ensure-pipeline-crons [$st]: registered closeout-resume"
  run "${DONE/done/$st}" "" "$INST"
  [ "$(resume_adds)" -eq 0 ] && pass "installer [$st]: no closeout-resume add" || fail "installer [$st]: registered closeout-resume"
done

echo "--- (2) budget spent -> no registration ---"
run "$OPEN" 60 "$ENS"
[ "$(resume_adds)" -eq 0 ] && pass "ensure-pipeline-crons [count 60]: no add" || fail "ensure-pipeline-crons registered with a spent budget"
run "$OPEN" 60 "$INST"
[ "$(resume_adds)" -eq 0 ] && pass "installer [count 60]: no add" || fail "installer registered with a spent budget"

echo "--- (3) fresh registration: one add, stale counter reset ---"
run "$OPEN" 10 "$ENS"
[ "$(resume_adds)" -eq 1 ] && pass "ensure-pipeline-crons [open]: one closeout-resume add" || fail "ensure-pipeline-crons [open]: expected exactly one add"
[ ! -e "$CNT" ] && pass "ensure-pipeline-crons: stale run counter reset" || fail "ensure-pipeline-crons left a stale run counter"
run "$OPEN" 10 "$INST"
[ "$(resume_adds)" -eq 1 ] && pass "installer [open]: one add" || fail "installer [open]: expected exactly one add"
[ ! -e "$CNT" ] && pass "installer: stale run counter reset" || fail "installer left a stale run counter"
run "$OPEN" "" "$INST"; run "$OPEN" "" "$INST"
printf '[{"name":"closeout-resume","id":"u1"}]' > "$SANDBOX/jobs.json"; : > "$SANDBOX/calls.log"
env -i PATH="$BIN:/usr/bin:/bin" HOME="$H" OC_ROOT="$H/.openclaw" FAKE_OC_JOBS_FILE="$SANDBOX/jobs.json" FAKE_OC_CALLS_FILE="$SANDBOX/calls.log" bash "$INST" >/dev/null 2>&1
[ "$(resume_adds)" -eq 0 ] && pass "installer [already present]: idempotent" || fail "installer duplicated a present cron"

echo "--- (3b) D10: unreadable cron list -> unknown -> installer does not register ---"
printf '%s' "$OPEN" > "$STATE"; : > "$SANDBOX/calls.log"
env -i PATH="$BIN:/usr/bin:/bin" HOME="$H" OC_ROOT="$H/.openclaw" FAKE_OC_LIST_MODE=fail FAKE_OC_JOBS_FILE="$SANDBOX/jobs.json" FAKE_OC_CALLS_FILE="$SANDBOX/calls.log" bash "$INST" >/dev/null 2>&1
[ "$(resume_adds)" -eq 0 ] && pass "installer [cron list fails]: no add" || fail "installer added on an unreadable cron list"

echo "--- (4) exhausted job sends nothing ---"
run "$OPEN" 60 "$H/.openclaw/skills/37-zhc-closeout/scripts/resume-closeout-cron.sh"
grep -q 'MAX RUNS EXCEEDED' "$SANDBOX/out.log" && pass "belt reached the exhausted branch" || fail "belt did not reach the exhausted branch ($(tail -2 "$SANDBOX/out.log" | tr '\n' ' '))"
if grep -E '^message send|message send' "$SANDBOX/calls.log" >/dev/null; then
  fail "exhausted belt sent a Telegram message"
else
  pass "exhausted belt sent no message (operator chat configured)"
fi

echo ""; echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
