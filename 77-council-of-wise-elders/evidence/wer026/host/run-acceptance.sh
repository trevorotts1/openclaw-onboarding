#!/usr/bin/env bash
# WER-026 live acceptance for the supervisor runner on this host.
# Every supervisor process started here is killed before the script returns.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
SUP="$REPO/77-council-of-wise-elders/scripts/supervisor"
RUNNER="$SUP/runner.mjs"
TMPROOT="/tmp/w13-u001-lane-wer026"
LOG="$HERE"

redact_file() {
  local operator_home="/Users/""blackceomacmini"
  sed -i '' "s#${operator_home}#<operator-home>#g" "$1"
}

state_get() { # <state.json> <dotted.path>
  node -e '
const fs = require("fs");
const state = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
let value = state;
for (const key of process.argv[2].split(".")) value = value?.[key];
console.log(typeof value === "object" && value !== null ? JSON.stringify(value) : value);
' "$1" "$2"
}

snapshot_outside_data() {
  find "$TMPROOT" -mindepth 1 \( -path "$TMPROOT/data-*" -prune \) -o -print 2>/dev/null | sort
  find "$TMPROOT" -mindepth 1 \( -path "$TMPROOT/data-*" -prune \) -o -type f -exec stat -f '%N %z %m' {} \; 2>/dev/null | sort
}

echo "== base =="
{
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "node=$(node --version)"
  echo "repo=$REPO"
  echo "head=$(git -C "$REPO" rev-parse HEAD)"
  echo "origin_main=$(git -C "$REPO" ls-remote origin refs/heads/main | awk '{print $1}')"
  echo "runner_sha256=$(shasum -a 256 "$RUNNER" | awk '{print $1}')"
} | tee "$LOG/00-base.txt" >/dev/null
cat "$LOG/00-base.txt"
git -C "$REPO" status --porcelain > "$LOG/00-git-status-before.txt"
echo "git_status_before_lines=$(wc -l < "$LOG/00-git-status-before.txt" | tr -d ' ')"

rm -rf "$TMPROOT"
mkdir -p "$TMPROOT"
snapshot_outside_data > "$LOG/01-temp-root-before.txt"
echo "temp_root_before_entries=$(wc -l < "$LOG/01-temp-root-before.txt" | tr -d ' ')"

echo
echo "== run A: two completed ticks, then kill -9 mid-tick =="
DATA_A="$TMPROOT/data-crash"
node "$RUNNER" --data-dir "$DATA_A" --interval-seconds 1 --lease-seconds 30 --tick-work-ms 1500 \
  > "$LOG/02-run-a-loop.log" 2>&1 &
PID_A=$!
echo "run_a_pid=$PID_A"

two_ticks=0
for _ in $(seq 1 400); do
  if [ -f "$DATA_A/state.json" ]; then
    completed="$(state_get "$DATA_A/state.json" completed_sweeps 2>/dev/null)"
    if [ "${completed:-0}" -ge 2 ] 2>/dev/null; then two_ticks=1; break; fi
  fi
  sleep 0.05
done
if [ "$two_ticks" -ne 1 ]; then echo "FAIL: two ticks not observed"; kill -9 "$PID_A" 2>/dev/null; exit 1; fi

pending=0
for _ in $(seq 1 400); do
  if [ -f "$DATA_A/state.json" ]; then
    count="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).restart_ledger.pending_actions.length)' "$DATA_A/state.json" 2>/dev/null)"
    if [ "${count:-0}" -ge 1 ]; then pending=1; break; fi
  fi
  sleep 0.02
done
if [ "$pending" -ne 1 ]; then echo "FAIL: no pending action window"; kill -9 "$PID_A" 2>/dev/null; exit 1; fi

cp "$DATA_A/state.json" "$LOG/03-pre-kill-state.json"
PRE_PENDING_ID="$(state_get "$DATA_A/state.json" 'restart_ledger.pending_actions.0.id')"
PRE_GEN="$(state_get "$DATA_A/state.json" ledger_generation)"
PRE_FENCE="$(state_get "$DATA_A/state.json" leader.fencing_generation)"
PRE_COMPLETED="$(state_get "$DATA_A/state.json" completed_sweeps)"
PRE_SCHEDULED="$(state_get "$DATA_A/state.json" planner.scheduled_sweeps)"
echo "pre_kill_pending_id=$PRE_PENDING_ID pre_gen=$PRE_GEN pre_fence=$PRE_FENCE pre_completed=$PRE_COMPLETED pre_scheduled=$PRE_SCHEDULED"

kill -9 "$PID_A"
wait "$PID_A"
RC_A=$?
echo "run_a_kill9_exit_code=$RC_A" | tee "$LOG/04-run-a-exit.txt"

echo
echo "== run B: restart on the same data dir, reconcile, one tick, --once =="
node "$RUNNER" --data-dir "$DATA_A" --interval-seconds 1 --lease-seconds 30 --once \
  > "$LOG/05-run-b-restart.log" 2>&1
RC_B=$?
echo "run_b_exit_code=$RC_B" | tee "$LOG/06-run-b-exit.txt"
cp "$DATA_A/state.json" "$LOG/07-post-restart-state.json"

POST_GEN="$(state_get "$DATA_A/state.json" ledger_generation)"
POST_FENCE="$(state_get "$DATA_A/state.json" leader.fencing_generation)"
POST_COMPLETED="$(state_get "$DATA_A/state.json" completed_sweeps)"
POST_INTERRUPTED="$(state_get "$DATA_A/state.json" interrupted_ticks)"
POST_PENDING="$(state_get "$DATA_A/state.json" 'restart_ledger.pending_actions')"
POST_SCHEDULED="$(state_get "$DATA_A/state.json" planner.scheduled_sweeps)"
POST_EXTRA="$(state_get "$DATA_A/state.json" planner.extra_sweeps)"
RECONCILED_COUNT="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).reconciled_actions.filter(a=>a.id===process.argv[2]).length)' "$DATA_A/state.json" "$PRE_PENDING_ID")"
RECONCILED_STATE="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");const a=JSON.parse(s).reconciled_actions.find(a=>a.id===process.argv[2]);console.log(a?a.state:"MISSING")' "$DATA_A/state.json" "$PRE_PENDING_ID")"
CONSUMED_ACTIONS="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).journal.actions.filter(a=>a.target===process.argv[2]).length)' "$DATA_A/state.json" "$PRE_PENDING_ID")"
RECONCILE_INCIDENTS="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).journal.incidents.filter(i=>i.kind==="INTERRUPTED_TICK_RECONCILED").length)' "$DATA_A/state.json")"
RECOVERY_KIND="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");const a=JSON.parse(s).journal.actions.find(a=>a.target===process.argv[2]);console.log(a?a.payload.decision_kind:"MISSING")' "$DATA_A/state.json" "$PRE_PENDING_ID")"
RECOVERY_CONSUMES_SLOT="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");const a=JSON.parse(s).journal.actions.find(a=>a.target===process.argv[2]);console.log(a?String(a.payload.consumes_scheduled_slot):"MISSING")' "$DATA_A/state.json" "$PRE_PENDING_ID")"
{
  echo "pre_pending_id=$PRE_PENDING_ID"
  echo "pre_ledger_generation=$PRE_GEN pre_fencing_generation=$PRE_FENCE pre_completed_sweeps=$PRE_COMPLETED pre_scheduled_sweeps=$PRE_SCHEDULED"
  echo "post_ledger_generation=$POST_GEN post_fencing_generation=$POST_FENCE post_completed_sweeps=$POST_COMPLETED post_scheduled_sweeps=$POST_SCHEDULED post_extra_sweeps=$POST_EXTRA"
  echo "post_interrupted_ticks=$POST_INTERRUPTED post_pending_actions=$POST_PENDING"
  echo "reconciled_records_for_pre_pending=$RECONCILED_COUNT reconciled_state=$RECONCILED_STATE"
  echo "journal_actions_targeting_pre_pending=$CONSUMED_ACTIONS reconciliation_incidents=$RECONCILE_INCIDENTS"
  echo "recovery_decision_kind=$RECOVERY_KIND recovery_consumes_scheduled_slot=$RECOVERY_CONSUMES_SLOT"
  echo "json_valid=$(node -e 'JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log("YES")' "$DATA_A/state.json")"
} | tee "$LOG/08-restart-summary.txt"

echo
echo "== run C: concurrent second instance, then graceful SIGTERM =="
DATA_C="$TMPROOT/data-single"
node "$RUNNER" --data-dir "$DATA_C" --interval-seconds 1 --lease-seconds 30 \
  > "$LOG/09-run-c-primary.log" 2>&1 &
PID_C=$!
echo "run_c_primary_pid=$PID_C"
for _ in $(seq 1 200); do
  grep -q '"event":"admitted"' "$LOG/09-run-c-primary.log" 2>/dev/null && break
  sleep 0.05
done

node "$RUNNER" --data-dir "$DATA_C" --interval-seconds 1 --lease-seconds 30 --once \
  > "$LOG/10-run-c-second-instance.log" 2>&1
RC_C2=$?
echo "run_c_second_instance_exit_code=$RC_C2" | tee "$LOG/11-second-instance-exit.txt"
SECOND_PID="$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).pid)' "$LOG/10-run-c-second-instance.log" 2>/dev/null)"

kill -TERM "$PID_C"
wait "$PID_C"
RC_C1=$?
echo "run_c_primary_sigterm_exit_code=$RC_C1" | tee "$LOG/12-sigterm-exit.txt"
cp "$DATA_C/state.json" "$LOG/13-post-sigterm-state.json"
{
  echo "second_instance_reason=$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).reason)' "$LOG/10-run-c-second-instance.log")"
  echo "second_instance_duplicate_start=$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).duplicate_start)' "$LOG/10-run-c-second-instance.log")"
  echo "second_instance_read_only=$(node -e 'const s=require("fs").readFileSync(process.argv[1],"utf8");console.log(JSON.parse(s).read_only)' "$LOG/10-run-c-second-instance.log")"
  echo "post_sigterm_supervisor_state=$(state_get "$DATA_C/state.json" supervisor.state)"
  echo "post_sigterm_admission_state=$(state_get "$DATA_C/state.json" admission.state)"
  echo "post_sigterm_stopped_at_ms=$(state_get "$DATA_C/state.json" stopped_at_ms)"
  echo "post_sigterm_json_valid=$(node -e 'JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log("YES")' "$DATA_C/state.json")"
} | tee "$LOG/14-singleton-and-stop-summary.txt"

echo
echo "== isolation: temp root snapshot and no network capability =="
snapshot_outside_data > "$LOG/15-temp-root-after.txt"
diff -u "$LOG/01-temp-root-before.txt" "$LOG/15-temp-root-after.txt" > "$LOG/16-temp-root-diff.txt"
RC_DIFF=$?
echo "temp_root_diff_exit_code=$RC_DIFF" | tee "$LOG/17-isolation-result.txt"
echo "outside_data_changed_lines=$(wc -l < "$LOG/16-temp-root-diff.txt" | tr -d ' ')" | tee -a "$LOG/17-isolation-result.txt"

grep -vE '^[[:space:]]*//' "$RUNNER" \
  | grep -nE 'child_process|node:(http|https|net|dns|tls|dgram)|fetch\(|XMLHttpRequest|WebSocket|EventSource|process\.env' \
  > "$LOG/18-forbidden-api-grep.txt" 2>&1
RC_GREP=$?
echo "forbidden_api_grep_exit_code=$RC_GREP (1 means no matches)" | tee "$LOG/19-forbidden-api-result.txt"
echo "temp_root_contents:" | tee -a "$LOG/19-forbidden-api-result.txt"
ls -la "$TMPROOT" | tee -a "$LOG/19-forbidden-api-result.txt"
echo "runner_import_lines:" | tee -a "$LOG/19-forbidden-api-result.txt"
grep -n '^import' "$RUNNER" | tee -a "$LOG/19-forbidden-api-result.txt"

echo
echo "== processes =="
ALIVE=0
for pid in "$PID_A" "$PID_C" ${SECOND_PID:+"$SECOND_PID"}; do
  if ps -p "$pid" >/dev/null 2>&1; then ALIVE=1; fi
done
echo "started_pids_still_alive=$ALIVE" | tee "$LOG/20-ps-started-pids.txt"
ps -p "$PID_A,$PID_C${SECOND_PID:+,$SECOND_PID}" -o pid,stat,command >> "$LOG/20-ps-started-pids.txt" 2>&1
cat "$LOG/20-ps-started-pids.txt"
ps -axo pid,stat,command | grep -F "runner.mjs --data-dir $TMPROOT" | grep -v grep > "$LOG/21-ps-runner-leftovers.txt" 2>&1
RC_PS=$?
echo "runner_leftovers_grep_exit_code=$RC_PS (1 means none)" | tee "$LOG/22-ps-result.txt"
cat "$LOG/21-ps-runner-leftovers.txt"

echo
echo "== tests =="
(cd "$SUP" && node --test tests/*.test.mjs) > "$LOG/26-existing-tests-only.txt" 2>&1
RC_TESTS_EXISTING=$?
echo "existing_tests_exit_code=$RC_TESTS_EXISTING" >> "$LOG/26-existing-tests-only.txt"
(cd "$SUP" && node --test tests/*.test.mjs runner.test.mjs) > "$LOG/23-tests.log" 2>&1
RC_TESTS=$?
echo "tests_exit_code=$RC_TESTS" | tee "$LOG/24-tests-result.txt"
tail -8 "$LOG/23-tests.log" | tee -a "$LOG/24-tests-result.txt"
grep -E '^ℹ (tests|pass|fail)' "$LOG/26-existing-tests-only.txt" | tee -a "$LOG/24-tests-result.txt"

git -C "$REPO" status --porcelain > "$LOG/25-git-status-after.txt"
echo "git_status_after_lines=$(wc -l < "$LOG/25-git-status-after.txt" | tr -d ' ')" | tee -a "$LOG/25-git-status-after.txt"

for file in "$LOG"/*.log "$LOG"/*.json "$LOG"/*.txt; do
  [ -f "$file" ] && redact_file "$file"
done

echo
echo "SUMMARY"
echo "run_a_kill9_exit_code=$RC_A"
echo "run_b_exit_code=$RC_B"
echo "second_instance_exit_code=$RC_C2"
echo "sigterm_exit_code=$RC_C1"
echo "temp_root_diff_exit_code=$RC_DIFF"
echo "forbidden_api_grep_exit_code=$RC_GREP"
echo "runner_leftovers_grep_exit_code=$RC_PS"
echo "tests_exit_code=$RC_TESTS"
exit 0
